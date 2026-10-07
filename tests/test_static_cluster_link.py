# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""
get_ips() with a STATIC cluster link (no avahi-autoipd ':avahi' label).

The alquiler1 cluster (now the taller `test`) pins its cluster link to static
169.254.0.x addresses so ProxyJump addresses never move; nodeconf only looked
for `bridge0:avahi` / `ethernet1:avahi` and so never found the link there.
"""
import importlib
import sys

import pytest


def _netifaces(table):
    """A netifaces stand-in serving `table` = {ifname_or_label: [ipv4, ...]}."""
    class FakeNetifaces:
        AF_INET = 2
        AF_LINK = 17

        @staticmethod
        def ifaddresses(name):
            if name not in table:
                raise ValueError(f"You must specify a valid interface name: {name}")
            addrs = table[name]
            return {2: [{'addr': a, 'netmask': '255.255.0.0'} for a in addrs]} if addrs else {}

        @staticmethod
        def interfaces():
            return ['lo'] + [n for n in table if ':' not in n]

        @staticmethod
        def gateways():
            return {'default': {}}
    return FakeNetifaces()


@pytest.fixture
def nodeconf_with(monkeypatch):
    def make(table):
        fake = _netifaces(table)
        monkeypatch.setitem(sys.modules, 'netifaces', fake)
        from cuemsnodeconf import CuemsNodeConf as cn_module
        importlib.reload(cn_module)
        monkeypatch.setattr(cn_module, 'netifaces', fake)
        return cn_module.CuemsNodeConf()
    return make


def test_labelled_bridge_still_wins(nodeconf_with):
    nc = nodeconf_with({'bridge0': ['169.254.13.233'], 'bridge0:avahi': ['169.254.13.233']})
    nc.get_ips()
    assert (nc.ip, nc.cluster_iface) == ('169.254.13.233', 'bridge0')


def test_static_node_bridge(nodeconf_with):
    """A node whose bridge0 carries a static 169.254 address and no label."""
    nc = nodeconf_with({'bridge0': ['169.254.0.11']})
    nc.get_ips()
    assert (nc.ip, nc.cluster_iface) == ('169.254.0.11', 'bridge0')
    assert nc.controller_ip is None


def test_static_controller_ethernet1(nodeconf_with):
    """A controller: static ethernet1 169.254.0.1 + bond0 on the venue LAN."""
    nc = nodeconf_with({'ethernet1': ['169.254.0.1'], 'bond0': ['10.16.10.2']})
    nc.get_ips()
    assert (nc.ip, nc.cluster_iface) == ('169.254.0.1', 'ethernet1')
    assert (nc.controller_ip, nc.ui_iface) == ('10.16.10.2', 'bond0')


def test_labelled_preferred_over_static(nodeconf_with):
    nc = nodeconf_with({'ethernet1': ['169.254.0.1'], 'ethernet1:avahi': ['169.254.9.204'], 'bond0': ['10.16.10.3']})
    nc.get_ips()
    assert (nc.ip, nc.cluster_iface) == ('169.254.9.204', 'ethernet1')


def test_ap_bridge_is_never_the_cluster_link(nodeconf_with):
    """A controller's AP bridge0 (192.168.6.1) must not be taken for the cluster link."""
    nc = nodeconf_with({'bridge0': ['192.168.6.1'], 'ethernet1': ['169.254.0.1'], 'bond0': ['10.16.10.2']})
    nc.get_ips()
    assert (nc.ip, nc.cluster_iface) == ('169.254.0.1', 'ethernet1')


def test_non_link_local_static_is_ignored(nodeconf_with, monkeypatch):
    """Only 169.254.x counts on a plain interface; otherwise keep waiting (and time out)."""
    from cuemsnodeconf import CuemsNodeConf as cn_module
    nc = nodeconf_with({'ethernet1': ['10.99.0.1'], 'bond0': ['10.16.10.2']})
    with pytest.raises(TimeoutError):
        nc.get_ips()
