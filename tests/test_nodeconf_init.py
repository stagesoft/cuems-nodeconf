"""
Tests for CuemsNodeConf initialization and basic setup.
"""
import pytest
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNodeDict


class TestNodeConfInitialization:
    """Test CuemsNodeConf initialization and basic setup."""
    
    def test_initialization(self):
        """Test that CuemsNodeConf initializes correctly."""
        nodeconf = CuemsNodeConf()
        
        assert nodeconf.network_map is not None
        assert isinstance(nodeconf.network_map, CuemsNodeDict)
        assert nodeconf.services == ['_cuems_nodeconf._tcp.local.']
        assert hasattr(nodeconf, 'map_path')
        assert hasattr(nodeconf, 'xsd_path')
    
    def test_get_ips_success(self):
        """Test successful IP detection."""
        nodeconf = CuemsNodeConf()
        nodeconf.get_ips()
        
        assert nodeconf.ip == '169.254.1.1', "Should detect bridge0:avahi"
        assert nodeconf.ip is not None
    
    def test_get_ips_priority(self):
        """Test that bridge0:avahi is preferred over ethernet1:avahi."""
        nodeconf = CuemsNodeConf()
        nodeconf.get_ips()
        
        # Should prefer bridge0:avahi (169.254.1.1) over ethernet1:avahi (169.254.2.1)
        assert nodeconf.ip == '169.254.1.1'

