"""
Pytest configuration and shared fixtures for cuems-nodeconf tests.
"""
import sys
import pytest

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

