"""The start-up window (feature 003, US1) and the self guard (US2).

set_comms() binds /tmp/nodeconf.ipc before run() loads the map, so for up to
the interface wait an adopt/unadopt can reach adopt_node with an EMPTY index
and be answered "Node <uuid> not found" — a confident, specific, wrong answer
about a node that is present. These tests exercise that window directly:
they send requests before, during and after read_network_map() and pin what
comes back (spec FR-001..FR-004, SC-001; contracts/readiness-response.md).

The comms thread is a MagicMock and asyncio.run_coroutine_threadsafe is
patched, the pattern tests/test_engine_callback.py uses: respond_to_engine's
argument is the response the engine would receive.
"""
from unittest.mock import MagicMock, patch

import pytest

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsutils.tools.ConfigManager import ConfigManager
from cuemsutils.tools.NodeList import NodeRole, node as Node

STARTING_UP = {'OK': False, 'error': 'nodeconf is still starting up'}
FIXTURE_CONTROLLER = '0367f391-ebf4-48b2-9f26-000000000001'   # online, adopted
FIXTURE_NODE = '0367f391-ebf4-48b2-9f26-000000000003'          # offline, not adopted


def _nodeconf():
    nodeconf = CuemsNodeConf()
    nodeconf.communications_thread = MagicMock()
    return nodeconf


def _send(nodeconf, message):
    """Deliver one request through engine_callback; return the response."""
    nodeconf.communications_thread.respond_to_engine.reset_mock()
    with patch('asyncio.run_coroutine_threadsafe'):
        nodeconf.engine_callback(message, MagicMock())
    return nodeconf.communications_thread.respond_to_engine.call_args[0][0]


def _modify(uuid, action='ADD'):
    return {'action': 'nodelist_modify', 'modify_action': action, 'value': uuid}


class TestTheWindow:
    """Before the map is loaded, adopt/unadopt are refused for the RIGHT reason."""

    @pytest.mark.parametrize('action', ['ADD', 'REMOVE'])
    def test_a_request_before_the_map_is_loaded_is_refused_as_starting_up(self, action):
        response = _send(_nodeconf(), _modify(FIXTURE_CONTROLLER, action))

        assert response == STARTING_UP

    @pytest.mark.parametrize('action', ['ADD', 'REMOVE'])
    def test_the_refusal_never_says_not_found(self, action):
        """The defect: a present node reported absent. The string must not read as a
        statement about the node at all."""
        response = _send(_nodeconf(), _modify(FIXTURE_CONTROLLER, action))

        assert 'not found' not in response['error']
        assert FIXTURE_CONTROLLER not in response['error']

    def test_the_refusal_keeps_the_response_contract(self):
        """{'OK': bool, 'error'?: str} — no new key (constitution IV)."""
        response = _send(_nodeconf(), _modify(FIXTURE_CONTROLLER))

        assert set(response) == {'OK', 'error'}
        assert response['OK'] is False
        assert isinstance(response['error'], str)


class TestOtherRequestsDuringTheWindow:
    """The gate narrows nothing: every other request answers as it always did."""

    def test_an_unknown_action_is_answered_as_before(self):
        response = _send(_nodeconf(), {'action': 'nodeconf'})
        assert response == {'OK': False, 'error': 'unknown action: nodeconf'}

    def test_a_missing_action_is_answered_as_before(self):
        response = _send(_nodeconf(), {'value': 'whatever'})
        assert response == {'OK': False, 'error': 'unknown action: None'}

    def test_a_non_dict_body_is_answered_as_before(self):
        response = _send(_nodeconf(), '')
        assert response['OK'] is False
        assert 'error' in response


class TestReadinessIsSetOnlyAfterBothHalves:
    """Ready means the document AND the index are installed; never a half-built state."""

    def test_the_daemon_is_not_ready_after_construction(self):
        assert _nodeconf()._ready is False

    def test_a_request_between_the_document_and_the_index_is_still_refused(self, cuems_conf_dir):
        """Story 1 scenario 4: the document is in, the index is not yet."""
        nodeconf = _nodeconf()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')
        seen = {}
        real_index = CuemsNodeConf._index_from_document

        def _index_then_capture(document):
            assert nodeconf._document is not None      # the document is already kept
            seen['response'] = _send(nodeconf, _modify(FIXTURE_CONTROLLER))
            return real_index(document)

        with patch.object(nodeconf, '_index_from_document', side_effect=_index_then_capture):
            nodeconf.read_network_map()

        assert seen['response'] == STARTING_UP

    def test_after_the_load_the_pre_feature_answers_return(self, cuems_conf_dir):
        nodeconf = _nodeconf()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')

        nodeconf.read_network_map()

        assert nodeconf._ready is True
        with patch.object(nodeconf, '_save_network_map'):
            assert _send(nodeconf, _modify(FIXTURE_CONTROLLER)) == {'OK': True}
            assert _send(nodeconf, _modify(FIXTURE_NODE)) == {
                'OK': False, 'error': f'Cannot adopt node {FIXTURE_NODE}: node is offline'}
            assert _send(nodeconf, _modify('no-such-uuid')) == {
                'OK': False, 'error': 'Node no-such-uuid not found'}

    def test_a_load_that_raises_leaves_the_daemon_not_ready(self, cuems_conf_dir):
        nodeconf = _nodeconf()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')

        with patch.object(ConfigManager, 'load_network_map', side_effect=RuntimeError('boom')):
            with pytest.raises(RuntimeError):
                nodeconf.read_network_map()

        assert nodeconf._ready is False
        assert _send(nodeconf, _modify(FIXTURE_CONTROLLER)) == STARTING_UP

    def test_readiness_never_reverts(self, cuems_conf_dir):
        """A later refresh or role change does not reopen the window (spec edge case)."""
        nodeconf = _nodeconf()
        nodeconf.map_path = str(cuems_conf_dir / 'network_map.xml')
        nodeconf.read_network_map()
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')

        with patch.object(nodeconf, '_save_network_map'):
            nodeconf.refresh_network_map()

        assert nodeconf._ready is True


class TestSelfGuard:
    """After discovery, the entry at our IP must carry the settings.xml uuid (FR-013).

    A different uuid at our IP is a stale record still being served while avahi
    reloads, or a foreign template. The lookup waits it out (constitution VI:
    exiting on first sight would lose the race against the reload every time
    the record changed) and refuses only on timeout, naming both uuids.
    """

    SETTINGS_UUID = '0367f391-ebf4-48b2-9f26-000000000001'
    STALE_UUID = 'a3811d78-099f-11f0-a075-00e04c01b7e3'

    def _nodeconf(self):
        nodeconf = CuemsNodeConf()
        nodeconf.ip = '169.254.1.1'
        nodeconf.settings_uuid = self.SETTINGS_UUID
        nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
        nodeconf.listener.nodes['controller._'] = Node(
            uuid=self.STALE_UUID, mac='controller._', name='controller',
            node_role=NodeRole.controller, ip='169.254.1.1', adopted=False, online=True)
        return nodeconf

    def test_a_stale_record_is_waited_out_and_the_matching_one_returned(self):
        nodeconf = self._nodeconf()
        fresh = Node(uuid=self.SETTINGS_UUID, mac='2cf05d21cca3', name='controller',
                     node_role=NodeRole.controller, ip='169.254.1.1', adopted=False, online=True)

        def two_iterations(**kwargs):
            yield 0
            nodeconf.listener.nodes['2cf05d21cca3'] = fresh   # avahi finished reloading
            yield 1

        with patch('cuemsnodeconf.CuemsNodeConf.TimeoutLoop', side_effect=two_iterations), \
             patch('cuemsnodeconf.CuemsNodeConf.Logger') as log:
            found = nodeconf.retreive_local_node()

        assert found is fresh
        warned = ' '.join(str(c.args[0]) for c in log.warning.call_args_list)
        assert self.STALE_UUID in warned and self.SETTINGS_UUID in warned

    def test_a_record_that_never_matches_is_refused_naming_both_uuids(self):
        nodeconf = self._nodeconf()

        with patch('cuemsnodeconf.CuemsNodeConf.TimeoutLoop', return_value=[0, 1]), \
             patch('cuemsnodeconf.CuemsNodeConf.Logger'):
            with pytest.raises(TimeoutError) as info:
                nodeconf.retreive_local_node()

        message = str(info.value)
        assert self.STALE_UUID in message and self.SETTINGS_UUID in message
        assert 'restart cuems-nodeconf' in message
