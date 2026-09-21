"""
Tests for engine callback functionality.
"""
import pytest
from unittest.mock import MagicMock, patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node
from cuemsutils.config.network_map import CuemsNetworkMapType


class TestEngineCallback:
    """Test engine callback functionality."""

    def test_engine_callback_adopt_node(self, tmp_path, monkeypatch):
        """Test engine callback for adopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Add a node to network_map
        node = Node(
            uuid='test-uuid-123',
            mac='testmac123456',
            name='test_node',
            node_role=NodeRole.node,
            ip='192.168.1.10',
            adopted=False,
        )
        nodeconf.network_map['testmac123456'] = node
        
        # Create mock context
        mock_context = MagicMock()
        mock_context.asend = MagicMock()
        
        # Create communications thread mock
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        
        message = {
            'action': 'nodelist_modify',
            'value': 'test-uuid-123',
            'modify_action': 'ADD'
        }
        
        with patch.object(nodeconf, 'adopt_node', return_value={'OK': True}) as mock_adopt, \
             patch('asyncio.run_coroutine_threadsafe'):
            
            nodeconf.engine_callback(message, mock_context)
            
            mock_adopt.assert_called_once_with('test-uuid-123')
    
    def test_engine_callback_unadopt_node(self, tmp_path, monkeypatch):
        """Test engine callback for unadopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')

        # Create mock context and thread
        mock_context = MagicMock()
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        
        message = {
            'action': 'nodelist_modify',
            'value': 'test-uuid-123',
            'modify_action': 'REMOVE'
        }
        
        with patch.object(nodeconf, 'unadopt_node', return_value={'OK': True}) as mock_unadopt, \
             patch('asyncio.run_coroutine_threadsafe'):
            
            nodeconf.engine_callback(message, mock_context)
            
            mock_unadopt.assert_called_once_with('test-uuid-123')
    
    def test_engine_callback_invalid_action(self):
        """Test engine callback with invalid modify_action."""
        nodeconf = CuemsNodeConf()
        
        # Create mock context and thread
        mock_context = MagicMock()
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        
        message = {
            'action': 'nodelist_modify',
            'value': 'test-uuid-123',
            'modify_action': 'INVALID'
        }
        
        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            nodeconf.engine_callback(message, mock_context)
            
            # Should call respond_to_engine with error
            assert mock_run.called
            call_args = mock_run.call_args[0][0]
            # The coroutine should send an error response
            assert call_args is not None
    
    def test_engine_callback_exception_handling(self):
        """Test that exceptions in engine_callback are handled gracefully."""
        nodeconf = CuemsNodeConf()
        
        # Create mock context and thread
        mock_context = MagicMock()
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        
        message = {
            'action': 'nodelist_modify',
            'value': 'test-uuid-123',
            'modify_action': 'ADD'
        }
        
        # Make adopt_node raise an exception
        with patch.object(nodeconf, 'adopt_node', side_effect=Exception("Test error")), \
             patch('asyncio.run_coroutine_threadsafe') as mock_run:
            
            # Should not raise, but handle the exception
            nodeconf.engine_callback(message, mock_context)
            
            # Should still call respond_to_engine with error response
            assert mock_run.called



class TestEveryRequestGetsAnAnswer:
    """A Req/Rep socket must never be left hanging.

    Before the else-branch in engine_callback, a well-formed message carrying
    any action other than 'nodelist_modify' returned without responding. The
    engine then blocked on its own 15 s IPC timeout and the operator saw an
    unexplained stall with nothing in either log to explain it.
    """

    def _nodeconf(self):
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf.communications_thread = MagicMock()
        nodeconf.communications_thread.event_loop = MagicMock()
        nodeconf.communications_thread.respond_to_engine = MagicMock()
        return nodeconf

    def test_unknown_action_is_answered(self):
        nodeconf = self._nodeconf()
        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            nodeconf.engine_callback({'action': 'nodeconf'}, MagicMock())

        assert mock_run.called, 'unknown action must still get a reply'
        response = nodeconf.communications_thread.respond_to_engine.call_args[0][0]
        assert response['OK'] is False
        assert 'unknown action' in response['error']
        assert 'nodeconf' in response['error']

    def test_missing_action_is_answered(self):
        nodeconf = self._nodeconf()
        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            nodeconf.engine_callback({'value': 'whatever'}, MagicMock())

        assert mock_run.called
        response = nodeconf.communications_thread.respond_to_engine.call_args[0][0]
        assert response['OK'] is False
        assert 'unknown action' in response['error']

    def test_non_dict_message_is_answered(self):
        """The editor's legacy `nodeconf` action arrives as a bare '' string."""
        nodeconf = self._nodeconf()
        with patch('asyncio.run_coroutine_threadsafe') as mock_run:
            nodeconf.engine_callback('', MagicMock())

        assert mock_run.called
        response = nodeconf.communications_thread.respond_to_engine.call_args[0][0]
        assert response['OK'] is False


class TestTheOperatorsOutcomeTable:
    """contracts/engine-rpc.md's outcome table, through the real dispatch path.

    adopt_node and unadopt_node run for real — only the map write is patched —
    so these pin the exact response cuems-frontend's settings component
    receives in every case (FR-009, FR-010), and that a successful change is
    saved BEFORE the answer goes out: an {'OK': True} for a change that is not
    on disk is a lie the operator cannot see.
    """

    def _nodeconf(self):
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = NodeIndex()
        nodeconf._document = CuemsNetworkMapType()  # feature 002: start-up loads this document; these tests skip start-up
        for mac, uuid, role, adopted, online in (
            ('controllermac', 'controller-uuid', NodeRole.controller, True, True),
            ('onlinemac1234', 'online-uuid', NodeRole.node, False, True),
            ('offlinemac123', 'offline-uuid', NodeRole.node, False, False),
            ('adoptedmac123', 'adopted-uuid', NodeRole.node, True, True),
        ):
            nodeconf.network_map[mac] = Node(
                uuid=uuid,
                mac=mac,
                name=mac,
                node_role=role,
                ip='192.168.1.10',
                adopted=adopted,
                online=online,
            )
        nodeconf.communications_thread = MagicMock()
        return nodeconf

    def _dispatch(self, nodeconf, modify_action, uuid):
        """Send one nodelist_modify; return (response, [save/respond in call order])."""
        order = MagicMock()
        with patch.object(CuemsNetworkMapType, 'save') as save, \
             patch('asyncio.run_coroutine_threadsafe'):
            order.attach_mock(save, 'save')
            order.attach_mock(nodeconf.communications_thread.respond_to_engine, 'respond')
            nodeconf.engine_callback(
                {'action': 'nodelist_modify', 'value': uuid, 'modify_action': modify_action},
                MagicMock(),
            )
        response = nodeconf.communications_thread.respond_to_engine.call_args[0][0]
        return response, [name for name, _args, _kwargs in order.mock_calls]

    def test_adopting_an_online_node_is_saved_then_answered_ok(self):
        nodeconf = self._nodeconf()
        response, calls = self._dispatch(nodeconf, 'ADD', 'online-uuid')
        assert response == {'OK': True}
        assert calls == ['save', 'respond']
        assert nodeconf.network_map['onlinemac1234']['adopted'] is True

    def test_adopting_an_already_adopted_node_is_answered_ok_without_a_write(self):
        response, calls = self._dispatch(self._nodeconf(), 'ADD', 'adopted-uuid')
        assert response == {'OK': True}
        assert calls == ['respond']

    def test_adopting_an_offline_node_is_refused(self):
        nodeconf = self._nodeconf()
        response, calls = self._dispatch(nodeconf, 'ADD', 'offline-uuid')
        assert response == {'OK': False, 'error': 'Cannot adopt node offline-uuid: node is offline'}
        assert calls == ['respond']
        assert nodeconf.network_map['offlinemac123']['adopted'] is False

    @pytest.mark.parametrize('modify_action', ['ADD', 'REMOVE'])
    def test_an_unknown_uuid_is_not_found(self, modify_action):
        response, calls = self._dispatch(self._nodeconf(), modify_action, 'no-such-uuid')
        assert response == {'OK': False, 'error': 'Node no-such-uuid not found'}
        assert calls == ['respond']

    def test_unadopting_a_node_is_saved_then_answered_ok(self):
        nodeconf = self._nodeconf()
        response, calls = self._dispatch(nodeconf, 'REMOVE', 'adopted-uuid')
        assert response == {'OK': True}
        assert calls == ['save', 'respond']
        assert nodeconf.network_map['adoptedmac123']['adopted'] is False

    def test_unadopting_an_already_unadopted_node_is_answered_ok_without_a_write(self):
        response, calls = self._dispatch(self._nodeconf(), 'REMOVE', 'online-uuid')
        assert response == {'OK': True}
        assert calls == ['respond']

    def test_unadopting_the_controller_is_refused(self):
        nodeconf = self._nodeconf()
        response, calls = self._dispatch(nodeconf, 'REMOVE', 'controller-uuid')
        assert response == {'OK': False, 'error': 'Cannot unadopt master node'}
        assert calls == ['respond']
        assert nodeconf.network_map['controllermac']['adopted'] is True

    def test_an_invalid_modify_action_is_refused(self):
        response, calls = self._dispatch(self._nodeconf(), 'INVALID', 'online-uuid')
        assert response == {'OK': False, 'error': 'Invalid modify_action: INVALID'}
        assert calls == ['respond']
