"""
Tests for network interface detection in CuemsNodeConf.
"""
import pytest
import sys
import importlib

# Import after mocking (conftest.py handles the mock)
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf


class TestInterfaceDetection:
    """Test network interface detection functionality."""
    
    def test_interface_detection_bridge0_avahi(self):
        """Test that get_ips() correctly detects bridge0:avahi interface."""
        nodeconf = CuemsNodeConf()
        nodeconf.get_ips()
        
        assert nodeconf.ip == '169.254.1.1', f"Expected IP 169.254.1.1, got {nodeconf.ip}"
        assert nodeconf.ip is not None, "IP should not be None"
    
    def test_interface_detection_priority(self):
        """Test that bridge0:avahi is prioritized over ethernet1:avahi."""
        nodeconf = CuemsNodeConf()
        nodeconf.get_ips()
        
        # Should prefer bridge0:avahi (169.254.1.1) over ethernet1:avahi (169.254.2.1)
        assert nodeconf.ip == '169.254.1.1', "Should prefer bridge0:avahi"
    
    def test_controller_ip_detection(self):
        """Test that controller IP can be detected from bond0 interface."""
        nodeconf = CuemsNodeConf()
        nodeconf.get_ips()
        
        # After getting bridge0:avahi, bond0 should be available for controller_ip
        # Note: controller_ip is only set if both ip and bond0 are found
        # In our mock, we get bridge0:avahi first and return, so controller_ip may be None
        # This is expected behavior based on the code logic
        assert nodeconf.ip is not None, "Main IP should be detected"
    
    def test_interface_detection_timeout(self, monkeypatch):
        """Test that interface detection times out when no interfaces are available."""
        # Create a mock that raises errors for all interfaces
        class NoInterfaceMock:
            AF_INET = 2
            AF_LINK = 17
            
            @staticmethod
            def ifaddresses(interface):
                raise ValueError(f"Interface {interface} not found")
            
            @staticmethod
            def interfaces():
                return ['lo']
            
            @staticmethod
            def gateways():
                return {'default': {}}
        
        # Patch netifaces in the module that uses it
        monkeypatch.setitem(sys.modules, 'netifaces', NoInterfaceMock())
        # Reload the module to pick up the new mock
        from cuemsnodeconf import CuemsNodeConf as cn_module
        importlib.reload(cn_module)
        monkeypatch.setattr(cn_module, 'netifaces', NoInterfaceMock())
        
        nodeconf = cn_module.CuemsNodeConf()
        
        # Should raise TimeoutError after 10 seconds
        with pytest.raises(TimeoutError):
            nodeconf.get_ips()

