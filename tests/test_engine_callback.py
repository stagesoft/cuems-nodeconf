# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""
Tests for engine callback functionality.
"""
import pytest
from unittest.mock import MagicMock, patch
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsNode import CuemsNode, CuemsNodeDict


class TestEngineCallback:
    """Test engine callback functionality."""
    
    def test_engine_callback_adopt_node(self, tmp_path, monkeypatch):
        """Test engine callback for adopting a node."""
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        
        # Add a node to network_map
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': False
        })
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
        nodeconf.network_map = CuemsNodeDict()
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
        nodeconf.network_map = CuemsNodeDict()
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


class TestMapWritesAreSerialized:
    """adopt/unadopt run on the comms thread while the worker loop writes the
    same map from the main thread, through the same temp path.
    """

    def _nodeconf_with_node(self, tmp_path, adopted=False, online=True):
        nodeconf = CuemsNodeConf()
        nodeconf.network_map = CuemsNodeDict()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        node = CuemsNode({
            'uuid': 'test-uuid-123',
            'mac': 'testmac123456',
            'name': 'test_node',
            'node_type': CuemsNode.NodeType.slave,
            'ip': '192.168.1.10',
            'adopted': adopted,
            'online': online,
        })
        nodeconf.network_map['testmac123456'] = node
        return nodeconf

    def test_adopt_holds_the_lock_while_writing(self, tmp_path):
        nodeconf = self._nodeconf_with_node(tmp_path)
        held = {}

        def _record(_map):
            # RLock has no public "is held by me", but acquire(blocking=False)
            # from this same thread succeeds only because it is re-entrant —
            # what we assert is that the write happens inside the with-block.
            held['locked'] = nodeconf._map_lock._is_owned()

        with patch.object(nodeconf, 'write_network_map', side_effect=_record):
            result = nodeconf.adopt_node('test-uuid-123')

        assert result == {'OK': True}
        assert held['locked'] is True

    def test_unadopt_holds_the_lock_while_writing(self, tmp_path):
        nodeconf = self._nodeconf_with_node(tmp_path, adopted=True)
        held = {}

        with patch.object(
            nodeconf, 'write_network_map',
            side_effect=lambda _m: held.__setitem__('locked', nodeconf._map_lock._is_owned())
        ):
            result = nodeconf.unadopt_node('test-uuid-123')

        assert result == {'OK': True}
        assert held['locked'] is True

    def test_adopt_updates_the_change_signature(self, tmp_path):
        """Otherwise the worker loop's next tick rewrites identical content."""
        nodeconf = self._nodeconf_with_node(tmp_path)
        with patch.object(nodeconf, 'write_network_map'):
            nodeconf.adopt_node('test-uuid-123')

        assert nodeconf._last_map_sig is not None
        assert nodeconf._last_map_sig == nodeconf._map_signature(nodeconf.network_map)

    def test_adopt_refuses_an_offline_node(self, tmp_path):
        nodeconf = self._nodeconf_with_node(tmp_path, online=False)
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.adopt_node('test-uuid-123')

        assert result['OK'] is False
        assert 'offline' in result['error']
        mock_write.assert_not_called()

    def test_unknown_uuid_is_not_found(self, tmp_path):
        nodeconf = self._nodeconf_with_node(tmp_path)
        with patch.object(nodeconf, 'write_network_map') as mock_write:
            result = nodeconf.adopt_node('no-such-uuid')

        assert result['OK'] is False
        assert 'not found' in result['error']
        mock_write.assert_not_called()


class TestStartupMapLoadIsGuarded:
    """start() spins up the comms thread BEFORE run() loads the map, so an
    adopt request can land while the map is being replaced. Startup is not
    instant — a master sleeps 5 s for slaves and may wait 30 s on firstrun
    nodes — so the window is real, and Tier-1 rollout restarts nodeconf.
    """

    def test_run_holds_the_lock_while_replacing_the_map(self, tmp_path, monkeypatch):
        nodeconf = CuemsNodeConf()
        nodeconf.map_path = str(tmp_path / 'network_map.xml')
        seen = {}

        def _record():
            seen['locked'] = nodeconf._map_lock._is_owned()
            nodeconf.network_map = CuemsNodeDict()

        monkeypatch.setattr(nodeconf, 'read_network_map', _record)
        (tmp_path / 'network_map.xml').write_text('<CuemsNetworkMap/>')

        # Drive only the map-load block of run(); everything after it needs
        # real interfaces and avahi.
        monkeypatch.setattr(nodeconf, 'get_ips', lambda: None)
        nodeconf.ip = '169.254.0.1'
        with pytest.raises(Exception):
            # Zeroconf() right after the block will fail in this environment;
            # by then the assertion we care about has already been recorded.
            nodeconf.run()

        assert seen.get('locked') is True
