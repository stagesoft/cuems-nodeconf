"""
Tests for CuemsAvahiListener functionality.
"""
import pytest
from unittest.mock import MagicMock, Mock
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict


class TestCuemsAvahiListener:
    """Test Avahi listener functionality."""
    
    def test_listener_initialization(self):
        """Test that CuemsAvahiListener initializes correctly."""
        listener = CuemsAvahiListener(ip='169.254.1.1')
        
        assert listener.ip == '169.254.1.1'
        assert listener.callback is None
        assert isinstance(listener.nodes, CuemsNodeDict)
    
    def test_get_mac(self):
        """Test MAC address extraction from service name."""
        listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Service names typically start with MAC address
        name = 'aabbccddeeff_service_name._cuems_nodeconf._tcp.local.'
        mac = listener.get_mac(name)
        
        assert mac == 'aabbccddeeff', f"Expected 'aabbccddeeff', got '{mac}'"
        assert len(mac) == 12, "MAC address should be 12 characters"
    
    def test_add_service_with_valid_info(self):
        """Test adding a service with valid service info."""
        listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Create mock service info
        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = ['169.254.1.1']
        mock_info.properties = {
            b'uuid': b'test-uuid-123',
            b'node_type': b'slave'
        }
        mock_info.port = 9000
        
        mock_zeroconf = MagicMock()
        mock_zeroconf.get_service_info.return_value = mock_info
        
        # Call add_service
        listener.add_service(mock_zeroconf, '_cuems_nodeconf._tcp.local.', 'aabbccddeeff_test._cuems_nodeconf._tcp.local.')
        
        # Verify node was added (MAC is first 12 chars of service name)
        assert 'aabbccddeeff' in listener.nodes
        node = listener.nodes['aabbccddeeff']
        assert node.uuid == 'test-uuid-123'
        assert node.ip == '169.254.1.1'
    
    def test_add_service_with_none_info(self):
        """Test that add_service handles None service info gracefully."""
        # Create a fresh listener to avoid state from other tests
        listener = CuemsAvahiListener(ip='169.254.1.1')
        listener.nodes = CuemsNodeDict()  # Reset nodes dict
        
        mock_zeroconf = MagicMock()
        mock_zeroconf.get_service_info.return_value = None
        
        # Should not raise exception, just return early
        listener.add_service(mock_zeroconf, '_cuems_nodeconf._tcp.local.', 'test_service')
        
        # No node should be added
        assert len(listener.nodes) == 0
    
    def test_add_service_with_missing_properties(self):
        """Test that add_service handles missing properties gracefully."""
        # Create a fresh listener to avoid state from other tests
        listener = CuemsAvahiListener(ip='169.254.1.1')
        listener.nodes = CuemsNodeDict()  # Reset nodes dict
        
        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = ['169.254.1.1']
        mock_info.properties = {}  # Missing required properties
        mock_info.port = 9000
        
        mock_zeroconf = MagicMock()
        mock_zeroconf.get_service_info.return_value = mock_info
        
        # Should not raise exception, just return early
        listener.add_service(mock_zeroconf, '_cuems_nodeconf._tcp.local.', 'test_service')
        
        # No node should be added
        assert len(listener.nodes) == 0
    
    def test_update_service_ip_selection(self):
        """Test that update_service correctly selects IP address."""
        listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # First add a service
        mock_info = MagicMock()
        mock_info.parsed_addresses.return_value = ['169.254.1.1']
        mock_info.properties = {
            b'uuid': b'test-uuid-123',
            b'node_type': b'slave'
        }
        mock_info.port = 9000
        
        mock_zeroconf = MagicMock()
        mock_zeroconf.get_service_info.return_value = mock_info
        
        listener.add_service(mock_zeroconf, '_cuems_nodeconf._tcp.local.', 'aabbccddeeff_test._cuems_nodeconf._tcp.local.')
        
        # Now update with multiple addresses - should prefer matching IP
        mock_info.parsed_addresses.return_value = ['192.168.1.1', '169.254.1.1', '10.0.0.1']
        
        listener.update_service(mock_zeroconf, '_cuems_nodeconf._tcp.local.', 'aabbccddeeff_test._cuems_nodeconf._tcp.local.')
        
        # Should use the matching IP (MAC is first 12 chars)
        node = listener.nodes['aabbccddeeff']
        assert node.ip == '169.254.1.1', "Should prefer IP matching listener's IP"

