"""
Tests for network map reading, writing, and merging operations.
"""
import pytest
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestNetworkMapOperations:
    """Test network map reading, writing, and merging."""
    
    def test_merge_discovered_nodes_new_node(self):
        """Test merging when a new node is discovered."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add a discovered node
        discovered_node = CuemsNode({
            'uuid': 'new-uuid',
            'mac': 'newmac123456',
            'name': 'new_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'online': True
        })
        nodeconf.listener.nodes['newmac123456'] = discovered_node
        
        nodeconf.merge_discovered_nodes()
        
        assert 'newmac123456' in nodeconf.network_map
        assert nodeconf.network_map['newmac123456'].adopted is False
        assert nodeconf.network_map['newmac123456'].online is True
    
    def test_merge_discovered_nodes_existing_node(self):
        """Test merging when an existing node is rediscovered."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add existing node to network_map
        existing_node = CuemsNode({
            'uuid': 'existing-uuid',
            'mac': 'existingmac12',
            'name': 'existing_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': True,
            'online': False
        })
        nodeconf.network_map['existingmac12'] = existing_node
        
        # Rediscover the node
        rediscovered_node = CuemsNode({
            'uuid': 'existing-uuid',
            'mac': 'existingmac12',
            'name': 'existing_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.11',  # IP changed
            'online': True
        })
        nodeconf.listener.nodes['existingmac12'] = rediscovered_node
        
        nodeconf.merge_discovered_nodes()
        
        # Adopted status should be preserved
        assert nodeconf.network_map['existingmac12'].adopted is True
        # Online status should be updated
        assert nodeconf.network_map['existingmac12'].online is True
        # IP should be updated
        assert nodeconf.network_map['existingmac12'].ip == '192.168.1.11'
    
    def test_merge_discovered_nodes_offline(self):
        """Test that nodes not discovered are marked offline."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add node to network_map but not to discovered nodes
        offline_node = CuemsNode({
            'uuid': 'offline-uuid',
            'mac': 'offlinemac123',
            'name': 'offline_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'online': True
        })
        nodeconf.network_map['offlinemac123'] = offline_node
        
        nodeconf.merge_discovered_nodes()
        
        assert nodeconf.network_map['offlinemac123'].online is False
    
    def test_set_master_always_adopted(self):
        """Test that master nodes are always marked as adopted."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.is_first_run = False
        
        # Add master and slave nodes
        master_node = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master_node',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
            'adopted': False
        })
        slave_node = CuemsNode({
            'uuid': 'slave-uuid',
            'mac': 'slavemac1234',
            'name': 'slave_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
            'adopted': False
        })
        nodeconf.network_map['mastermac123'] = master_node
        nodeconf.network_map['slavemac1234'] = slave_node
        
        nodeconf.set_master_always_adopted()
        
        assert nodeconf.network_map['mastermac123'].adopted is True
        # Slave should remain False (not first run)
        assert nodeconf.network_map['slavemac1234'].adopted is False
    
    def test_set_master_always_adopted_first_run(self):
        """Test that on first run, non-master nodes are not adopted."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.is_first_run = True
        
        # Add master and slave nodes
        master_node = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master_node',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
            'adopted': True  # Was adopted
        })
        slave_node = CuemsNode({
            'uuid': 'slave-uuid',
            'mac': 'slavemac1234',
            'name': 'slave_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
            'adopted': True  # Was adopted
        })
        nodeconf.network_map['mastermac123'] = master_node
        nodeconf.network_map['slavemac1234'] = slave_node
        
        nodeconf.set_master_always_adopted()
        
        assert nodeconf.network_map['mastermac123'].adopted is True
        # On first run, non-masters should be False
        assert nodeconf.network_map['slavemac1234'].adopted is False

