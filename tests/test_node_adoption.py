"""
Tests for node adoption and unadoption functionality.
"""
import pytest
from unittest.mock import patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node
from cuemsutils.config.network_map import CuemsNetworkMapType


class TestNodeAdoption:
    """Test node adoption and unadoption functionality."""

    def test_adopt_node_success(self, tmp_path, monkeypatch):
        """Test successfully adopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf._document = CuemsNetworkMapType()  # feature 002: start-up loads this document; these tests skip start-up
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add a node to network_map (must be online to be adoptable)
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=False,
            online=True,
        )
        nodeconf.network_map['testmac123456'] = node

        with patch.object(CuemsNetworkMapType, 'save'):
            result = nodeconf.adopt_node('test-uuid-123')

            assert result['OK'] is True
            assert nodeconf.network_map['testmac123456']['adopted'] is True

    def test_adopt_node_not_found(self):
        """Test adopting a node that doesn't exist."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()

        result = nodeconf.adopt_node('nonexistent-uuid')

        assert result['OK'] is False
        assert 'error' in result
        assert 'not found' in result['error']

    def test_adopt_node_already_adopted(self, tmp_path):
        """Test adopting a node that is already adopted."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add an already adopted node
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=True,
            online=True,
        )
        nodeconf.network_map['testmac123456'] = node

        # Try to adopt again - should return success but not write network map
        with patch.object(CuemsNetworkMapType, 'save') as mock_write:
            result = nodeconf.adopt_node('test-uuid-123')

            assert result['OK'] is True
            assert 'message' in result
            assert 'already adopted' in result['message']
            # Should not write network map since nothing changed
            assert not mock_write.called
            # Node should still be adopted
            assert nodeconf.network_map['testmac123456']['adopted'] is True

    def test_adopt_node_offline(self, tmp_path):
        """Test adopting an offline node should fail."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add an offline node
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=False,
            online=False,
        )
        nodeconf.network_map['testmac123456'] = node

        # Try to adopt - should fail
        with patch.object(CuemsNetworkMapType, 'save') as mock_write:
            result = nodeconf.adopt_node('test-uuid-123')

            assert result['OK'] is False
            assert 'error' in result
            assert 'offline' in result['error']
            # Should not write network map since adoption failed
            assert not mock_write.called
            # Node should still not be adopted
            assert nodeconf.network_map['testmac123456']['adopted'] is False

    def test_unadopt_node_success(self, tmp_path, monkeypatch):
        """Test successfully unadopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf._document = CuemsNetworkMapType()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add an adopted node (must be online)
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=True,
            online=True,
        )
        nodeconf.network_map['testmac123456'] = node

        with patch.object(CuemsNetworkMapType, 'save'):
            result = nodeconf.unadopt_node('test-uuid-123')

            assert result['OK'] is True
            assert nodeconf.network_map['testmac123456']['adopted'] is False

    def test_unadopt_node_already_unadopted(self, tmp_path):
        """Test unadopting a node that is already unadopted."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add an already unadopted node
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=False,
            online=True,
        )
        nodeconf.network_map['testmac123456'] = node

        # Try to unadopt again - should return success but not write network map
        with patch.object(CuemsNetworkMapType, 'save') as mock_write:
            result = nodeconf.unadopt_node('test-uuid-123')

            assert result['OK'] is True
            assert 'message' in result
            assert 'already unadopted' in result['message']
            # Should not write network map since nothing changed
            assert not mock_write.called
            # Node should still be unadopted
            assert nodeconf.network_map['testmac123456']['adopted'] is False

    def test_unadopt_node_offline(self, tmp_path):
        """Test unadopting an offline node (should succeed with warning)."""
        nodeconf = CuemsNodeConf()
        nodeconf._document = CuemsNetworkMapType()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add an adopted but offline node
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=True,
            online=False,
        )
        nodeconf.network_map['testmac123456'] = node

        # Try to unadopt - should succeed (offline nodes can be unadopted)
        with patch.object(CuemsNetworkMapType, 'save') as mock_write:
            result = nodeconf.unadopt_node('test-uuid-123')

            assert result['OK'] is True
            # Should write network map since node was unadopted
            assert mock_write.called
            # Node should now be unadopted
            assert nodeconf.network_map['testmac123456']['adopted'] is False

    def test_unadopt_master_node_fails(self):
        """Test that unadopting a controller node fails."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()

        # Add an adopted controller node
        controller_node = Node(
            uuid='controller-uuid',
            mac='mastermac123',
            name='controller_node',
            node_role=NodeRole.controller,
            ip='192.168.1.1',
            adopted=True,
        )
        nodeconf.network_map['mastermac123'] = controller_node

        result = nodeconf.unadopt_node('controller-uuid')

        assert result['OK'] is False
        assert 'error' in result
        assert 'Cannot unadopt master node' in result['error']
        # Controller should still be adopted
        assert nodeconf.network_map['mastermac123']['adopted'] is True

    def test_unadopt_node_not_found(self):
        """Test unadopting a node that doesn't exist."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()

        result = nodeconf.unadopt_node('nonexistent-uuid')

        assert result['OK'] is False
        assert 'error' in result
        assert 'not found' in result['error']

    def test_adopt_node_writes_a_schema_valid_map_end_to_end(self, cuems_conf_dir):
        """T068 (SC-008): adoption's write path is exercised for real — no
        mocking the map save — and the result round-trips through
        ``read_network_map``, which fails loudly (``SchemaError``) if the
        written document does not validate against ``network_map.xsd``.
        """
        nodeconf = CuemsNodeConf()
        nodeconf._document = CuemsNetworkMapType()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')

        node = Node(
            uuid='12345678-1234-5678-1234-567812345678',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=False,
            online=True,
        )
        nodeconf.network_map['testmac123456'] = node

        result = nodeconf.adopt_node('12345678-1234-5678-1234-567812345678')
        assert result['OK'] is True

        reread = CuemsNodeConf()
        reread._document = CuemsNetworkMapType()
        reread.map_path = nodeconf.map_path
        reread.read_network_map()

        written_node = reread.network_map['testmac123456']
        assert written_node['adopted'] is True
        assert written_node['node_role'] is NodeRole.node
        assert written_node['uuid'] == '12345678-1234-5678-1234-567812345678'
