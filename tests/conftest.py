"""
Pytest configuration and shared fixtures for cuems-nodeconf tests.
"""
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Patch dbus BEFORE any imports that might use it (feature 007, T067-T079).
#
# dbus-python is a compiled extension (dbus-gmain, built against libdbus-1)
# that a pyenv-managed dev interpreter typically cannot import without
# libdbus-1-dev installed and a from-source build — a real dependency on a
# packaged node (via dh_virtualenv --use-system-packages, see pyproject.toml),
# absent in a plain dev checkout. CuemsNodeConf.py's only use of it is
# SystemBus()/Interface()/exceptions.DBusException around systemd unit
# management (~line 730) — not exercised by the node-model tests this
# feature adds — so a minimal stub unblocks importing the module at all
# without needing the real binding. DBusException must be a real exception
# type (not a MagicMock) because `except dbus.exceptions.DBusException` is
# only legal Python if the caught object is a *class* deriving from
# BaseException.
if 'dbus' not in sys.modules:
    _dbus_stub = types.ModuleType('dbus')
    _dbus_stub.SystemBus = MagicMock(name='dbus.SystemBus')
    _dbus_stub.Interface = MagicMock(name='dbus.Interface')
    # AliasPublisher.ensure() wraps a flags int in dbus.UInt32 before the
    # D-Bus call; the real type is an int subclass, so plain int stands in.
    _dbus_stub.UInt32 = int
    _dbus_exceptions_stub = types.ModuleType('dbus.exceptions')

    class DBusException(Exception):
        pass

    _dbus_exceptions_stub.DBusException = DBusException
    _dbus_stub.exceptions = _dbus_exceptions_stub
    sys.modules['dbus'] = _dbus_stub
    sys.modules['dbus.exceptions'] = _dbus_exceptions_stub

# Patch systemd for the same reason as dbus, above.
#
# systemd-python is a compiled extension built against libsystemd; pip cannot
# build it without libsystemd-dev, which a plain dev checkout has no reason to
# carry (on a packaged node it arrives as python3-systemd via
# dh_virtualenv --use-system-packages, see pyproject.toml). CuemsNodeConf.py's
# only use is notify_systemd() -> systemd.daemon.notify('READY=1'), the
# Type=notify handshake — meaningless outside a real unit and not exercised by
# any test — so a MagicMock stands in. Tests that care assert on the call.
if 'systemd' not in sys.modules:
    _systemd_stub = types.ModuleType('systemd')
    _systemd_daemon_stub = types.ModuleType('systemd.daemon')
    _systemd_daemon_stub.notify = MagicMock(name='systemd.daemon.notify')
    _systemd_stub.daemon = _systemd_daemon_stub
    sys.modules['systemd'] = _systemd_stub
    sys.modules['systemd.daemon'] = _systemd_daemon_stub

# Patch netifaces BEFORE any imports that might use it
# This needs to happen at module load time, not in a fixture

# Define constants (standard netifaces values)
AF_INET = 2
AF_LINK = 17


def mock_ifaddresses(interface):
    """Mock ifaddresses to return expected interfaces."""
    mock_addrs = {
        'bridge0:avahi': {
            AF_INET: [{'addr': '169.254.1.1', 'netmask': '255.255.0.0'}],
            AF_LINK: [{'addr': 'aa:bb:cc:dd:ee:ff'}]
        },
        'ethernet1:avahi': {
            AF_INET: [{'addr': '169.254.2.1', 'netmask': '255.255.0.0'}],
            AF_LINK: [{'addr': '11:22:33:44:55:66'}]
        },
        'bond0': {
            AF_INET: [{'addr': '192.168.1.100', 'netmask': '255.255.255.0'}],
            AF_LINK: [{'addr': 'aa:aa:aa:aa:aa:aa'}]
        }
    }
    
    if interface in mock_addrs:
        return mock_addrs[interface]
    else:
        raise ValueError(f"Interface {interface} not found")


class MockNetifaces:
    """Mock netifaces module for testing."""
    AF_INET = AF_INET
    AF_LINK = AF_LINK
    
    @staticmethod
    def ifaddresses(interface):
        return mock_ifaddresses(interface)
    
    @staticmethod
    def interfaces():
        return ['bridge0:avahi', 'ethernet1:avahi', 'bond0', 'lo']
    
    @staticmethod
    def gateways():
        return {
            'default': {
                AF_INET: ('192.168.1.1', 'bond0')
            }
        }


# Patch netifaces at module level so it's available before any imports
_original_netifaces = sys.modules.get('netifaces')
sys.modules['netifaces'] = MockNetifaces()

@pytest.fixture(scope='function', autouse=True)
def mock_netifaces(monkeypatch):
    """
    Automatically mock netifaces for all tests.
    This ensures network interface detection works in test environment.
    """
    # Ensure netifaces is mocked in sys.modules
    monkeypatch.setitem(sys.modules, 'netifaces', MockNetifaces())
    
    # Also patch it in any modules that might have already imported it
    # This is needed because CuemsNodeConf imports netifaces at module level.
    #
    # Import lazily and tolerate failure: CuemsNodeConf pulls in dbus, zeroconf
    # and systemd at module level, none of which the pure-model tests need. An
    # unconditional import here made *every* test in the suite error out on a
    # machine missing any one of them (dbus in particular needs libdbus-1-dev to
    # build from source). Tests that actually exercise CuemsNodeConf still fail
    # loudly on their own import.
    try:
        from cuemsnodeconf import CuemsNodeConf
    except ImportError:
        pass
    else:
        if hasattr(CuemsNodeConf, 'netifaces'):
            monkeypatch.setattr(CuemsNodeConf, 'netifaces', MockNetifaces())

    yield MockNetifaces()


CUEMS_CONF_FIXTURES = Path(__file__).parent / 'fixtures' / 'etc_cuems'


@pytest.fixture
def cuems_conf_dir(tmp_path, monkeypatch):
    """A private /etc/cuems for one test, provisioned the way every node is.

    cuems-nodeconf never runs standalone: on a node, its cuems-utils and
    cuems-common dependencies guarantee /etc/cuems holds settings.xml and
    network_map.xml, and read_network_map loads the map through ConfigManager,
    which requires settings.xml. This copies both fixtures into tmp_path and
    points CUEMS_CONF_PATH at it, so nothing in the test reaches the real
    /etc/cuems. Returns tmp_path; a test that needs a file missing deletes it.
    """
    for name in ('settings.xml', 'network_map.xml'):
        shutil.copy(CUEMS_CONF_FIXTURES / name, tmp_path / name)
    monkeypatch.setenv('CUEMS_CONF_PATH', str(tmp_path))
    return tmp_path


@pytest.fixture
def cuems_conf_dir_empty(tmp_path, monkeypatch):
    """A private /etc/cuems whose map lists no nodes — a freshly installed node.

    This is what cuems-common actually ships (an empty <node_list/>, since its
    f78c876 removed the placeholder controller), so it is the map every fresh
    install boots against. `cuems_conf_dir`'s map is populated, which is why
    nothing here exercised this path: the daemon crash-looped on it until
    cuems-utils e363d03, and no fixture in this repository could show it
    (feature 002, research R6).

    network_map_empty.xml is byte-identical to the shipped file; keep it that
    way, and keep it the same bytes the daemon seeds.
    """
    shutil.copy(CUEMS_CONF_FIXTURES / 'settings.xml', tmp_path / 'settings.xml')
    shutil.copy(CUEMS_CONF_FIXTURES / 'network_map_empty.xml',
                tmp_path / 'network_map.xml')
    monkeypatch.setenv('CUEMS_CONF_PATH', str(tmp_path))
    return tmp_path
