"""
Tests for CuemsNodeDict properties (masters, slaves, firstruns).
"""
import pytest
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict


class TestNodeDictProperties:
    """Test CuemsNodeDict properties (masters, slaves, firstruns)."""
    
    def test_node_dict_masters_property(self):
        """Test that masters property returns only master nodes."""
        node_dict = CuemsNodeDict()
        
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
        
        node_dict['mastermac123'] = master
        node_dict['slavemac1234'] = slave
        
        masters = node_dict.masters
        assert len(masters) == 1
        assert masters[0].node_type == CuemsNode.NodeType.master
    
    def test_node_dict_slaves_property(self):
        """Test that slaves property returns only slave nodes."""
        node_dict = CuemsNodeDict()
        
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
        
        node_dict['mastermac123'] = master
        node_dict['slavemac1234'] = slave
        
        slaves = node_dict.slaves
        assert len(slaves) == 1
        assert slaves[0].node_type == CuemsNode.NodeType.slave
    
    def test_node_dict_firstruns_property(self):
        """Test that firstruns property returns only firstrun nodes."""
        node_dict = CuemsNodeDict()
        
        firstrun = CuemsNode({
            'uuid': 'firstrun-uuid',
            'mac': 'firstrunmac12',
            'name': 'firstrun',
            'node_type': CuemsNode.NodeType.firstrun,
            'ip': '192.168.1.3',
        })
        slave = CuemsNode({
            'uuid': 'slave-uuid',
            'mac': 'slavemac1234',
            'name': 'slave',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.2',
        })
        
        node_dict['firstrunmac12'] = firstrun
        node_dict['slavemac1234'] = slave
        
        firstruns = node_dict.firstruns
        assert len(firstruns) == 1
        assert firstruns[0].node_type == CuemsNode.NodeType.firstrun

