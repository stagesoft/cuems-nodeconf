"""
Integration tests for CuemsNodeConf covering end-to-end scenarios.
"""
import pytest
from unittest.mock import MagicMock, patch, Mock
import sys

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener


class TestIntegrationScenarios:
    """Integration tests for complete workflows."""
    
    def test_first_run_becomes_master_scenario(self, tmp_path, monkeypatch):
        """Test complete first-run scenario where node becomes master."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.map_path = str(tmp_path / 'network_map.xml')  # First run - no file
        
        # Setup listener with no masters
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = CuemsNodeDict()
        
        # Create local firstrun node
        local_node = CuemsNode({
            'uuid': 'local-uuid',
            'mac': 'localmac1234',
            'name': 'local_node',
            'node_type': CuemsNode.NodeType.firstrun,
            'ip': '169.254.1.1',
        })
        nodeconf.listener.nodes['localmac1234'] = local_node
        nodeconf.node = local_node
        
        # Mock all external operations
        with patch('shutil.copy2'), \
             patch.object(nodeconf, 'change_network_to_master', return_value=True), \
             patch.object(nodeconf, 'get_ips'), \
             patch.object(nodeconf, 'write_network_map'), \
             patch.object(nodeconf, 'update_master_lock_file'), \
             patch.object(nodeconf, 'notify_systemd'):
            
            # Simulate set_node_type
            nodeconf.set_node_type()
            
            assert nodeconf.node.node_type == CuemsNode.NodeType.master
    
    def test_slave_node_discovers_master_scenario(self):
        """Test scenario where slave node discovers master."""
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        
        # Add master node to discovered nodes
        master_node = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master_node',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
        })
        nodeconf.listener.nodes['mastermac123'] = master_node
        
        # Add local slave node
        local_node = CuemsNode({
            'uuid': 'local-uuid',
            'mac': 'localmac1234',
            'name': 'local_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '169.254.1.1',
        })
        nodeconf.listener.nodes['localmac1234'] = local_node
        
        # Check nodes
        nodeconf.check_nodes()
        
        # Verify master is detected
        assert len(nodeconf.listener.nodes.masters) == 1
        assert nodeconf.listener.nodes.masters[0].uuid == 'master-uuid'
    
    def test_node_adoption_workflow(self, tmp_path):
        """Test complete node adoption workflow."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add discovered node
        discovered_node = CuemsNode({
            'uuid': 'discovered-uuid',
            'mac': 'discoveredmac',
            'name': 'discovered_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': False
        })
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes['discoveredmac'] = discovered_node
        
        # Merge discovered nodes
        nodeconf.merge_discovered_nodes()
        
        # Adopt the node
        with patch.object(nodeconf, 'write_network_map'):
            result = nodeconf.adopt_node('discovered-uuid')
            
            assert result['OK'] is True
            assert nodeconf.network_map['discoveredmac'].adopted is True
    
    def test_master_slave_network_merge(self):
        """Test merging network map with master and slave nodes."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.is_first_run = False
        
        # Add master and slave to discovered nodes
        master = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
        })
        slave = CuemsNode({
            'uuid': 'slave-uuid',
            'mac': 'slavemac1234',
            'name': 'slave',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
        })
        nodeconf.listener.nodes['mastermac123'] = master
        nodeconf.listener.nodes['slavemac1234'] = slave
        
        # Merge and set master as adopted
        nodeconf.merge_discovered_nodes()
        nodeconf.set_master_always_adopted()
        
        # Verify master is adopted, slave is not
        assert nodeconf.network_map['mastermac123'].adopted is True
        assert nodeconf.network_map['slavemac1234'].adopted is False
        assert nodeconf.network_map['mastermac123'].online is True
        assert nodeconf.network_map['slavemac1234'].online is True
    
    def test_large_network_with_multiple_slaves(self):
        """Test network with master and multiple slave nodes."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()  # Ensure fresh network map
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = CuemsNodeDict()  # Ensure fresh listener nodes
        nodeconf.is_first_run = False
        
        # Add master node
        master = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
        })
        
        # Add multiple slave nodes
        slave1 = CuemsNode({
            'uuid': 'slave1-uuid',
            'mac': 'slave1mac123',
            'name': 'slave1',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
        })
        slave2 = CuemsNode({
            'uuid': 'slave2-uuid',
            'mac': 'slave2mac456',
            'name': 'slave2',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.3',
        })
        slave3 = CuemsNode({
            'uuid': 'slave3-uuid',
            'mac': 'slave3mac789',
            'name': 'slave3',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.4',
        })
        
        nodeconf.listener.nodes['mastermac123'] = master
        nodeconf.listener.nodes['slave1mac123'] = slave1
        nodeconf.listener.nodes['slave2mac456'] = slave2
        nodeconf.listener.nodes['slave3mac789'] = slave3
        
        # Merge and set master as adopted
        nodeconf.merge_discovered_nodes()
        nodeconf.set_master_always_adopted()
        
        # Verify all nodes are in network map
        assert len(nodeconf.network_map) == 4
        assert 'mastermac123' in nodeconf.network_map
        assert 'slave1mac123' in nodeconf.network_map
        assert 'slave2mac456' in nodeconf.network_map
        assert 'slave3mac789' in nodeconf.network_map
        
        # Verify master is adopted, slaves are not
        assert nodeconf.network_map['mastermac123'].adopted is True
        assert nodeconf.network_map['slave1mac123'].adopted is False
        assert nodeconf.network_map['slave2mac456'].adopted is False
        assert nodeconf.network_map['slave3mac789'].adopted is False
        
        # Verify all nodes are online
        assert nodeconf.network_map['mastermac123'].online is True
        assert nodeconf.network_map['slave1mac123'].online is True
        assert nodeconf.network_map['slave2mac456'].online is True
        assert nodeconf.network_map['slave3mac789'].online is True
        
        # Verify node type properties
        assert len(nodeconf.listener.nodes.masters) == 1
        assert len(nodeconf.listener.nodes.slaves) == 3
    
    def test_network_with_mixed_node_types(self):
        """Test network with master, slaves, and firstrun nodes."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()  # Ensure fresh network map
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = CuemsNodeDict()  # Ensure fresh listener nodes
        nodeconf.is_first_run = False
        
        # Add master
        master = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
        })
        
        # Add adopted slaves
        slave1 = CuemsNode({
            'uuid': 'slave1-uuid',
            'mac': 'slave1mac123',
            'name': 'slave1',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
            'adopted': True
        })
        slave2 = CuemsNode({
            'uuid': 'slave2-uuid',
            'mac': 'slave2mac456',
            'name': 'slave2',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.3',
            'adopted': True
        })
        
        # Add firstrun node (new node joining network)
        firstrun = CuemsNode({
            'uuid': 'firstrun-uuid',
            'mac': 'firstrunmac789',
            'name': 'firstrun',
            'node_type': CuemsNode.NodeType.firstrun,
            'ip': '192.168.1.4',
        })
        
        # Pre-populate network_map with adopted slaves (simulating existing network)
        nodeconf.network_map['slave1mac123'] = slave1
        nodeconf.network_map['slave2mac456'] = slave2
        
        # Now add all nodes to listener (rediscovery)
        nodeconf.listener.nodes['mastermac123'] = master
        nodeconf.listener.nodes['slave1mac123'] = slave1
        nodeconf.listener.nodes['slave2mac456'] = slave2
        nodeconf.listener.nodes['firstrunmac789'] = firstrun
        
        # Merge nodes (should preserve adopted status for existing nodes)
        nodeconf.merge_discovered_nodes()
        nodeconf.set_master_always_adopted()
        
        # Verify all nodes are present
        assert len(nodeconf.network_map) == 4
        
        # Verify node types
        assert len(nodeconf.listener.nodes.masters) == 1
        assert len(nodeconf.listener.nodes.slaves) == 2
        assert len(nodeconf.listener.nodes.firstruns) == 1
        
        # Verify adoption status
        assert nodeconf.network_map['mastermac123'].adopted is True
        assert nodeconf.network_map['slave1mac123'].adopted is True  # Was already adopted, preserved
        assert nodeconf.network_map['slave2mac456'].adopted is True  # Was already adopted, preserved
        assert nodeconf.network_map['firstrunmac789'].adopted is False  # Firstrun not adopted
    
    def test_network_with_nodes_going_offline(self):
        """Test network where some nodes go offline."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()  # Ensure fresh network map
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = CuemsNodeDict()  # Ensure fresh listener nodes
        nodeconf.is_first_run = False
        
        # Initially all nodes are online
        master = CuemsNode({
            'uuid': 'master-uuid',
            'mac': 'mastermac123',
            'name': 'master',
            'node_type': CuemsNode.NodeType.master,
            'ip': '192.168.1.1',
            'online': True
        })
        slave1 = CuemsNode({
            'uuid': 'slave1-uuid',
            'mac': 'slave1mac123',
            'name': 'slave1',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
            'online': True
        })
        slave2 = CuemsNode({
            'uuid': 'slave2-uuid',
            'mac': 'slave2mac456',
            'name': 'slave2',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.3',
            'online': True
        })
        
        # Add all to network map
        nodeconf.network_map['mastermac123'] = master
        nodeconf.network_map['slave1mac123'] = slave1
        nodeconf.network_map['slave2mac456'] = slave2
        
        # First merge - all online
        nodeconf.listener.nodes['mastermac123'] = master
        nodeconf.listener.nodes['slave1mac123'] = slave1
        nodeconf.listener.nodes['slave2mac456'] = slave2
        nodeconf.merge_discovered_nodes()
        
        assert nodeconf.network_map['mastermac123'].online is True
        assert nodeconf.network_map['slave1mac123'].online is True
        assert nodeconf.network_map['slave2mac456'].online is True
        
        # Second merge - slave2 goes offline (not in discovered nodes)
        nodeconf.listener.nodes = CuemsNodeDict()
        nodeconf.listener.nodes['mastermac123'] = master
        nodeconf.listener.nodes['slave1mac123'] = slave1
        # slave2 is missing - not in discovered nodes
        nodeconf.merge_discovered_nodes()
        
        # slave2 should be marked offline
        assert nodeconf.network_map['mastermac123'].online is True
        assert nodeconf.network_map['slave1mac123'].online is True
        assert nodeconf.network_map['slave2mac456'].online is False
    
    def test_adopting_multiple_nodes_in_sequence(self, tmp_path):
        """Test adopting multiple nodes one after another."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()  # Ensure fresh network map
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes = CuemsNodeDict()  # Ensure fresh listener nodes
        
        # Add multiple discovered nodes
        slave1 = CuemsNode({
            'uuid': 'slave1-uuid',
            'mac': 'slave1mac123',
            'name': 'slave1',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
            'adopted': False
        })
        slave2 = CuemsNode({
            'uuid': 'slave2-uuid',
            'mac': 'slave2mac456',
            'name': 'slave2',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.3',
            'adopted': False
        })
        slave3 = CuemsNode({
            'uuid': 'slave3-uuid',
            'mac': 'slave3mac789',
            'name': 'slave3',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.4',
            'adopted': False
        })
        
        nodeconf.listener.nodes['slave1mac123'] = slave1
        nodeconf.listener.nodes['slave2mac456'] = slave2
        nodeconf.listener.nodes['slave3mac789'] = slave3
        
        # Merge discovered nodes
        nodeconf.merge_discovered_nodes()
        
        # Adopt nodes one by one
        with patch.object(nodeconf, 'write_network_map'):
            result1 = nodeconf.adopt_node('slave1-uuid')
            assert result1['OK'] is True
            assert nodeconf.network_map['slave1mac123'].adopted is True
            
            result2 = nodeconf.adopt_node('slave2-uuid')
            assert result2['OK'] is True
            assert nodeconf.network_map['slave2mac456'].adopted is True
            
            result3 = nodeconf.adopt_node('slave3-uuid')
            assert result3['OK'] is True
            assert nodeconf.network_map['slave3mac789'].adopted is True
        
        # Verify all are adopted
        assert nodeconf.network_map['slave1mac123'].adopted is True
        assert nodeconf.network_map['slave2mac456'].adopted is True
        assert nodeconf.network_map['slave3mac789'].adopted is True

