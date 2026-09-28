"""The configured start-up waits and the pre-flight (feature 003, US6 — the polish phase).

Two environment variables, read once at start with the historical values as
defaults, and a pre-flight that names a missing system bus or avahi before
the socket exists — a diagnostic, never an exit: the unit already declares
Requires=avahi-daemon.service (spec FR-023/FR-024; research R7, R12).
"""
from unittest.mock import MagicMock, patch

import pytest

import cuemsnodeconf.CuemsNodeConf as daemon_module
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf


class TestConfiguredWaits:
    def test_defaults_are_the_historical_values(self, monkeypatch):
        monkeypatch.delenv('CUEMS_NODECONF_IFACE_TIMEOUT', raising=False)
        monkeypatch.delenv('CUEMS_NODECONF_CONTROLLER_PAUSE', raising=False)
        nodeconf = CuemsNodeConf()

        assert nodeconf._iface_timeout() == 10
        assert nodeconf._controller_pause() == 5

    def test_the_environment_overrides_them(self, monkeypatch):
        monkeypatch.setenv('CUEMS_NODECONF_IFACE_TIMEOUT', '3')
        monkeypatch.setenv('CUEMS_NODECONF_CONTROLLER_PAUSE', '0')
        nodeconf = CuemsNodeConf()

        assert nodeconf._iface_timeout() == 3
        assert nodeconf._controller_pause() == 0

    @pytest.mark.parametrize('value', ['abc', '-1', '', '2.5'])
    def test_garbage_falls_back_to_the_default_with_a_warning(self, monkeypatch, value):
        monkeypatch.setenv('CUEMS_NODECONF_IFACE_TIMEOUT', value)
        nodeconf = CuemsNodeConf()

        with patch.object(daemon_module, 'Logger') as log:
            assert nodeconf._iface_timeout() == 10
        assert log.warning.called
        assert 'CUEMS_NODECONF_IFACE_TIMEOUT' in log.warning.call_args[0][0]

    def test_get_ips_uses_the_configured_wait(self, monkeypatch):
        monkeypatch.setenv('CUEMS_NODECONF_IFACE_TIMEOUT', '3')
        nodeconf = CuemsNodeConf()

        with patch.object(daemon_module, 'TimeoutLoop', return_value=[0]) as loop:
            nodeconf.get_ips()

        assert loop.call_args[1]['timeout'] == 3


class TestPreflight:
    def _dbus_exception(self):
        import dbus
        return dbus.exceptions.DBusException

    def test_an_unreachable_system_bus_is_named_and_not_fatal(self):
        nodeconf = CuemsNodeConf()
        with patch.object(daemon_module, 'Logger') as log, \
             patch.object(daemon_module.dbus, 'SystemBus', side_effect=self._dbus_exception()('no bus')):
            nodeconf._preflight()

        assert 'system bus' in log.error.call_args[0][0]

    def test_a_silent_avahi_is_named_and_not_fatal(self):
        nodeconf = CuemsNodeConf()
        server = MagicMock()
        server.GetVersionString.side_effect = self._dbus_exception()('no avahi')
        with patch.object(daemon_module, 'Logger') as log, \
             patch.object(daemon_module.dbus, 'SystemBus'), \
             patch.object(daemon_module.dbus, 'Interface', return_value=server):
            nodeconf._preflight()

        assert 'avahi-daemon' in log.error.call_args[0][0]

    def test_a_healthy_node_logs_nothing_at_error(self):
        nodeconf = CuemsNodeConf()
        server = MagicMock()
        server.GetVersionString.return_value = 'avahi 0.8'
        with patch.object(daemon_module, 'Logger') as log, \
             patch.object(daemon_module.dbus, 'SystemBus'), \
             patch.object(daemon_module.dbus, 'Interface', return_value=server):
            nodeconf._preflight()

        log.error.assert_not_called()

    def test_preflight_runs_before_identity_and_socket(self, cuems_conf_dir, avahi_dirs):
        nodeconf = CuemsNodeConf()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')
        calls = []
        with patch.object(nodeconf, '_preflight', side_effect=lambda: calls.append('preflight')), \
             patch.object(nodeconf, '_load_identity', side_effect=lambda: calls.append('identity')), \
             patch.object(nodeconf, '_render_service_record',
                          side_effect=lambda role: calls.append('render') or False), \
             patch.object(nodeconf, 'set_comms', side_effect=lambda: calls.append('set_comms')), \
             patch.object(nodeconf, 'run'):
            nodeconf.start()

        assert calls == ['preflight', 'identity', 'render', 'set_comms']
