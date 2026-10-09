# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Interface-scoped avahi alias publisher.

Publishes static A records (e.g. controller.local, formitgo.local) via avahi's
D-Bus EntryGroup API, bound to a SPECIFIC network interface.

Why D-Bus and not `avahi-publish -a`: the CLI publishes the record on EVERY
interface (it has no per-interface option). On a multihomed CUEMS controller
that leaks the cluster link-local address onto the UI network and vice-versa,
violating RFC 6762 §6.2 ("a responder MUST NOT include addresses that are not
valid on the interface on which it is sending"). macOS clients are the most
sensitive to the resulting unreachable A record. EntryGroup.AddAddress takes an
explicit interface index, so the record is only ever answered on that link.

The publisher is idempotent and self-healing: ensure() re-publishes when the IP
changes (IPv4LL renegotiation) or when the avahi daemon has restarted (the
EntryGroup is lost and must be recreated).
"""

import dbus

from cuemsutils.log import Logger

# avahi enum constants (avahi-common/address.h, defs.h) — hardcoded to avoid a
# dependency on the python3-avahi helper module.
IF_UNSPEC = -1
PROTO_INET = 0
PROTO_UNSPEC = -1

# Publish ONLY the forward A record; never let avahi add the reverse PTR. A UI
# alias (e.g. formitgo.local) shares its address with the host's own hostname
# record (controller.local on bond0), whose reverse PTR for that IP avahi
# already owns; a second reverse for the same address collides ("Local name
# collision"). NO_REVERSE keeps the alias forward-only. (avahi-common/defs.h
# AvahiPublishFlags.)
AVAHI_PUBLISH_NO_REVERSE = 0x10

ENTRY_GROUP_UNCOMMITED = 0
ENTRY_GROUP_REGISTERING = 1
ENTRY_GROUP_ESTABLISHED = 2
ENTRY_GROUP_COLLISION = 3
ENTRY_GROUP_FAILURE = 4

AVAHI_DBUS_NAME = 'org.freedesktop.Avahi'
AVAHI_DBUS_PATH_SERVER = '/'
AVAHI_DBUS_IFACE_SERVER = 'org.freedesktop.Avahi.Server'
AVAHI_DBUS_IFACE_ENTRY_GROUP = 'org.freedesktop.Avahi.EntryGroup'


class AliasPublisher:
    """Manages a set of interface-scoped avahi A records, keyed by alias name."""

    def __init__(self):
        self._bus = None
        self._server = None
        # name -> {'ip', 'iface', 'group'(dbus.Interface)}
        self._records = {}

    # -- D-Bus plumbing -----------------------------------------------------
    def _connect(self):
        """(Re)acquire the avahi Server proxy. Cheap to call repeatedly."""
        if self._server is not None:
            return True
        try:
            self._bus = dbus.SystemBus()
            self._server = dbus.Interface(
                self._bus.get_object(AVAHI_DBUS_NAME, AVAHI_DBUS_PATH_SERVER),
                AVAHI_DBUS_IFACE_SERVER,
            )
            return True
        except dbus.exceptions.DBusException as e:
            Logger.error(f"AliasPublisher: cannot reach avahi over D-Bus: {e}")
            self._bus = None
            self._server = None
            return False

    def _iface_index(self, ifname):
        try:
            return int(self._server.GetNetworkInterfaceIndexByName(ifname))
        except dbus.exceptions.DBusException as e:
            Logger.warning(f"AliasPublisher: avahi has no interface {ifname!r} yet: {e}")
            return None

    def _group_state(self, group):
        try:
            return int(group.GetState())
        except dbus.exceptions.DBusException:
            # avahi-daemon likely restarted; the group handle is stale.
            return None

    # -- public API ---------------------------------------------------------
    def ensure(self, name, ip, ifname):
        """Ensure ``name`` resolves to ``ip`` on interface ``ifname`` only.

        Idempotent: a no-op if the record is already established with the same
        ip/iface; otherwise (new, changed ip, or avahi restarted) it (re)commits.
        """
        if not self._connect():
            return False

        existing = self._records.get(name)
        if existing is not None:
            state = self._group_state(existing['group'])
            if (existing['ip'] == ip and existing['iface'] == ifname
                    and state in (ENTRY_GROUP_REGISTERING, ENTRY_GROUP_ESTABLISHED)):
                return True  # already correct
            # Stale (ip changed / avahi restarted / collision) — tear it down.
            self._reset(name)

        idx = self._iface_index(ifname)
        if idx is None:
            return False

        try:
            group_path = self._server.EntryGroupNew()
            group = dbus.Interface(
                self._bus.get_object(AVAHI_DBUS_NAME, group_path),
                AVAHI_DBUS_IFACE_ENTRY_GROUP,
            )
            group.AddAddress(idx, PROTO_INET, dbus.UInt32(AVAHI_PUBLISH_NO_REVERSE), name, ip)
            group.Commit()
            self._records[name] = {'ip': ip, 'iface': ifname, 'group': group}
            Logger.info(f"AliasPublisher: published {name} -> {ip} on {ifname} (idx {idx})")
            return True
        except dbus.exceptions.DBusException as e:
            Logger.error(f"AliasPublisher: failed publishing {name} -> {ip} on {ifname}: {e}")
            # Drop the server handle so the next call reconnects from scratch.
            self._server = None
            return False

    def _reset(self, name):
        rec = self._records.pop(name, None)
        if rec is None:
            return
        try:
            rec['group'].Reset()
            rec['group'].Free()
        except dbus.exceptions.DBusException:
            pass  # stale handle (avahi restarted) — nothing to free

    def close(self):
        for name in list(self._records.keys()):
            self._reset(name)
        self._records.clear()
        self._server = None
        self._bus = None
