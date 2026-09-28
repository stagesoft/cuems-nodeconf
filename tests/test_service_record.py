"""The mDNS service record is rendered from settings.xml (feature 003, US2).

cuems-nodeconf is the sole writer of /etc/avahi/services/cuems.service. It
renders the role template cuems-common ships (which carries the sentinel
uuid) over the identity in /etc/cuems/settings.xml, before it binds its
request socket, and refuses to start at all when the node is unprovisioned
(spec FR-010..FR-012; contracts/service-record-render.md; research R3/R4).

Paths: the avahi_dirs fixture points TEMPLATES_PATH and AVAHI_SERVICES_PATH
at tmp_path, so nothing here touches /usr/share/cuems or /etc/avahi. Logging:
the module's Logger is patched with a MagicMock and its calls inspected.
"""
import os
import stat
from unittest.mock import MagicMock, patch

import pytest

import cuemsnodeconf.CuemsNodeConf as daemon_module
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf, SENTINEL_UUID, SENTINEL_MAC
from cuemsutils.tools.NodeList import NodeRole

FIXTURE_UUID = '0367f391-ebf4-48b2-9f26-000000000001'
FIXTURE_MAC = '2cf05d21cca3'


def _nodeconf(conf_dir):
    nodeconf = CuemsNodeConf()
    nodeconf.map_path = str(conf_dir / 'network_map.xml')
    return nodeconf


def _rendered(share, role):
    return (share / f'cuems.service.{role.value}').read_bytes().replace(
        SENTINEL_UUID.encode(), FIXTURE_UUID.encode())


class TestTheSentinelsArePinned:
    """The library defines these in an internal module; the daemon carries its own copy."""

    def test_the_sentinel_values_match_the_011_contract(self):
        assert SENTINEL_UUID == '00000000-0000-0000-0000-000000000000'
        assert len(SENTINEL_UUID) == 36
        assert SENTINEL_MAC == '000000000000'


class TestRender:
    def test_the_record_is_the_template_with_the_sentinel_replaced(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()

        with patch.object(nodeconf, '_reload_avahi') as reload:
            changed = nodeconf._render_service_record(NodeRole.node)

        live = services / 'cuems.service'
        assert changed is True
        assert live.read_bytes() == _rendered(share, NodeRole.node)
        assert SENTINEL_UUID.encode() not in live.read_bytes()
        assert live.read_bytes().count(FIXTURE_UUID.encode()) == 2
        assert reload.call_count == 1

    def test_the_record_is_readable_by_the_avahi_user(self, cuems_conf_dir, avahi_dirs):
        """Constitution I: root writes it, avahi-daemon (user avahi) reads it."""
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()

        previous = os.umask(0o077)
        try:
            with patch.object(nodeconf, '_reload_avahi'):
                nodeconf._render_service_record(NodeRole.controller)
        finally:
            os.umask(previous)

        assert stat.S_IMODE((services / 'cuems.service').stat().st_mode) == 0o644

    def test_the_write_is_atomic_and_leaves_nothing_behind(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()

        with patch.object(nodeconf, '_reload_avahi'):
            nodeconf._render_service_record(NodeRole.firstrun)

        assert [p.name for p in services.iterdir()] == ['cuems.service']

    def test_an_unchanged_record_is_neither_written_nor_reloaded(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()
        with patch.object(nodeconf, '_reload_avahi'):
            nodeconf._render_service_record(NodeRole.node)
        live = services / 'cuems.service'
        before = live.stat().st_mtime_ns

        with patch.object(nodeconf, '_reload_avahi') as reload:
            changed = nodeconf._render_service_record(NodeRole.node)

        assert changed is False
        assert live.stat().st_mtime_ns == before
        reload.assert_not_called()

    def test_a_role_change_rewrites_and_reloads(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()
        with patch.object(nodeconf, '_reload_avahi'):
            nodeconf._render_service_record(NodeRole.firstrun)

        with patch.object(nodeconf, '_reload_avahi') as reload:
            changed = nodeconf._render_service_record(NodeRole.controller)

        assert changed is True
        assert (services / 'cuems.service').read_bytes() == _rendered(share, NodeRole.controller)
        assert reload.call_count == 1

    def test_the_templates_are_read_from_templates_path(self, cuems_conf_dir, avahi_dirs):
        """The shipped templates are cuems-common's package content; nothing else is read."""
        share, services = avahi_dirs
        (share / 'cuems.service.node').write_bytes(
            b'<service-group><txt-record>uuid=' + SENTINEL_UUID.encode() + b'</txt-record></service-group>')
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()

        with patch.object(nodeconf, '_reload_avahi'):
            nodeconf._render_service_record(NodeRole.node)

        assert (services / 'cuems.service').read_bytes() == (
            b'<service-group><txt-record>uuid=' + FIXTURE_UUID.encode() + b'</txt-record></service-group>')

    def test_a_failed_reload_is_logged_and_does_not_stop_the_daemon(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()
        import dbus

        with patch.object(daemon_module, 'Logger') as log, \
             patch.object(daemon_module.dbus, 'SystemBus', side_effect=dbus.exceptions.DBusException('no bus')):
            changed = nodeconf._render_service_record(NodeRole.node)

        assert changed is True
        assert (services / 'cuems.service').exists()
        assert log.error.called


class TestRenderRefusals:
    def test_a_template_without_the_sentinel_is_refused(self, cuems_conf_dir, avahi_dirs):
        """A template carrying a real uuid predates cuems-common 1.3.0-23; never announce it."""
        share, services = avahi_dirs
        template = share / 'cuems.service.node'
        template.write_bytes(template.read_bytes().replace(
            SENTINEL_UUID.encode(), b'a3811d78-099f-11f0-a075-00e04c01b7e3'))
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()

        with patch.object(daemon_module, 'Logger') as log, \
             patch.object(nodeconf, '_reload_avahi'):
            with pytest.raises(SystemExit) as exit_info:
                nodeconf._render_service_record(NodeRole.node)

        assert exit_info.value.code != 0
        assert not (services / 'cuems.service').exists()
        assert str(template) in log.critical.call_args[0][0]

    def test_a_missing_template_is_refused_naming_it(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        (share / 'cuems.service.node').unlink()
        nodeconf = _nodeconf(cuems_conf_dir)
        nodeconf._load_identity()

        with patch.object(daemon_module, 'Logger') as log:
            with pytest.raises(SystemExit):
                nodeconf._render_service_record(NodeRole.node)

        assert 'cuems.service.node' in log.critical.call_args[0][0]


class TestUnprovisionedRefusesToStart:
    """No settings, unreadable settings, invalid settings, or the sentinel identity:
    NOT PROVISIONED, exit non-zero, no socket, no record (FR-011, SC-004)."""

    def _start(self, nodeconf):
        with patch.object(daemon_module, 'Logger') as log, \
             patch.object(nodeconf, 'set_comms') as set_comms, \
             patch.object(nodeconf, 'run') as run:
            with pytest.raises(SystemExit) as exit_info:
                nodeconf.start()
        return exit_info.value.code, log, set_comms, run

    def _assert_refused(self, code, log, set_comms, run, services):
        assert code != 0
        set_comms.assert_not_called()
        run.assert_not_called()
        assert list(services.iterdir()) == []
        assert log.critical.call_args[0][0].startswith('NOT PROVISIONED')

    def test_an_absent_settings_file(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        (cuems_conf_dir / 'settings.xml').unlink()
        self._assert_refused(*self._start(_nodeconf(cuems_conf_dir)), services)

    def test_an_unreadable_settings_file(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        with patch.object(daemon_module, 'ConfigManager',
                          side_effect=PermissionError(13, 'Permission denied')):
            self._assert_refused(*self._start(_nodeconf(cuems_conf_dir)), services)

    def test_an_invalid_settings_file(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        (cuems_conf_dir / 'settings.xml').write_text('<broken/>')
        self._assert_refused(*self._start(_nodeconf(cuems_conf_dir)), services)

    def test_the_sentinel_identity(self, cuems_conf_dir_sentinel, avahi_dirs):
        share, services = avahi_dirs
        self._assert_refused(*self._start(_nodeconf(cuems_conf_dir_sentinel)), services)

    def test_a_sentinel_mac_alone_is_refused(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        settings = cuems_conf_dir / 'settings.xml'
        settings.write_text(settings.read_text().replace(f'<mac>{FIXTURE_MAC}</mac>',
                                                         f'<mac>{SENTINEL_MAC}</mac>'))
        self._assert_refused(*self._start(_nodeconf(cuems_conf_dir)), services)

    def test_a_provisioned_node_starts(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        nodeconf = _nodeconf(cuems_conf_dir)
        with patch.object(nodeconf, 'set_comms') as set_comms, \
             patch.object(nodeconf, 'run') as run, \
             patch.object(nodeconf, '_reload_avahi'):
            nodeconf.start()

        assert nodeconf.settings_uuid == FIXTURE_UUID
        assert nodeconf.settings_mac == FIXTURE_MAC
        set_comms.assert_called_once()
        run.assert_called_once()
        assert (services / 'cuems.service').exists()


class TestRenderHappensBeforeTheSocket:
    """Contract startup-order.md steps 3 and 4: a refusal never leaves a socket behind."""

    def test_the_record_is_rendered_before_set_comms(self, cuems_conf_dir, avahi_dirs):
        nodeconf = _nodeconf(cuems_conf_dir)
        calls = []
        with patch.object(nodeconf, '_render_service_record',
                          side_effect=lambda role: calls.append('render') or False), \
             patch.object(nodeconf, 'set_comms', side_effect=lambda: calls.append('set_comms')), \
             patch.object(nodeconf, 'run'):
            nodeconf.start()

        assert calls == ['render', 'set_comms']


class TestStartupRenderKeepsTheLiveRole:
    """The start-up render corrects the uuid; the role stays what the live record says."""

    def _live(self, avahi_dirs, role):
        share, services = avahi_dirs
        (services / 'cuems.service').write_bytes(_rendered(share, role))

    def test_a_controller_record_stays_controller(self, cuems_conf_dir, avahi_dirs):
        self._live(avahi_dirs, NodeRole.controller)
        assert _nodeconf(cuems_conf_dir)._live_record_role() == NodeRole.controller

    def test_a_node_record_stays_node(self, cuems_conf_dir, avahi_dirs):
        self._live(avahi_dirs, NodeRole.node)
        assert _nodeconf(cuems_conf_dir)._live_record_role() == NodeRole.node

    def test_no_live_record_means_firstrun(self, cuems_conf_dir, avahi_dirs):
        assert _nodeconf(cuems_conf_dir)._live_record_role() == NodeRole.firstrun

    def test_an_unparseable_record_means_firstrun(self, cuems_conf_dir, avahi_dirs):
        share, services = avahi_dirs
        (services / 'cuems.service').write_bytes(b'<service-group><txt-record>node_role=master</txt-record></service-group>')
        assert _nodeconf(cuems_conf_dir)._live_record_role() == NodeRole.firstrun

    def test_start_renders_the_live_role(self, cuems_conf_dir, avahi_dirs):
        self._live(avahi_dirs, NodeRole.node)
        nodeconf = _nodeconf(cuems_conf_dir)
        with patch.object(nodeconf, '_render_service_record', return_value=False) as render, \
             patch.object(nodeconf, 'set_comms'), patch.object(nodeconf, 'run'):
            nodeconf.start()

        render.assert_called_once_with(NodeRole.node)
