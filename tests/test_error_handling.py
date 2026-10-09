"""
Tests for error handling in various scenarios.
"""
import pytest
import sys
import importlib
from unittest.mock import patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf


class TestErrorHandling:
    """Test error handling in various scenarios."""
    
    def test_get_ips_timeout(self, monkeypatch):
        """Test that get_ips times out when no interfaces available."""
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
        
        monkeypatch.setitem(sys.modules, 'netifaces', NoInterfaceMock())
        from cuemsnodeconf import CuemsNodeConf as cn_module
        importlib.reload(cn_module)
        monkeypatch.setattr(cn_module, 'netifaces', NoInterfaceMock())
        
        nodeconf = cn_module.CuemsNodeConf()
        
        # Should raise TimeoutError after timeout
        with pytest.raises(TimeoutError):
            nodeconf.get_ips()
    
    def test_run_exits_on_no_ip(self, monkeypatch, tmp_path):
        """Test that run() exits when IP cannot be obtained."""
        nodeconf = CuemsNodeConf()
        nodeconf.map_path = str(tmp_path / 'nonexistent_map.xml')  # Ensure file doesn't exist
        
        # Mock get_ips to set ip to None
        def mock_get_ips():
            nodeconf.ip = None
        
        with patch.object(nodeconf, 'get_ips', side_effect=mock_get_ips), \
             patch('os.path.isfile', return_value=False):
            
            # run() will call sys.exit(-1) when ip is None, which raises SystemExit
            with pytest.raises(SystemExit) as exc_info:
                nodeconf.run()
            
            # Verify it exited with code -1
            assert exc_info.value.code == -1

