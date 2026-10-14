# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""
node_set — the operator's node alias, written by the map's only writer.

The brief is specs/planning/12-node-set-alias.md; its section 3 is the contract
these tests pin, row by row, through the real dispatch path (engine_callback
-> alias_node -> NodeIndex.set_alias -> the map on disk). Only the IPC reply is
captured; the map is written for real, so "no write" is checked on the file's
bytes and mtime, not on a mock.
"""
import json
import os
import time
from unittest.mock import MagicMock, patch

import pytest

from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node

CONTROLLER = '0367f391-ebf4-48b2-9f26-0000000000c1'
ONLINE = '0367f391-ebf4-48b2-9f26-0000000000a1'
OFFLINE = '0367f391-ebf4-48b2-9f26-0000000000a2'
UNKNOWN = '0367f391-ebf4-48b2-9f26-0000000000ff'


def _nodeconf(tmp_path, ready=True):
    nodeconf = CuemsNodeConf()
    nodeconf._ready = ready
    nodeconf._document = CuemsNetworkMapType()
    nodeconf.network_map = NodeIndex()
    nodeconf.listener = CuemsAvahiListener(ip='169.254.0.1')
    nodeconf.map_path = str(tmp_path / 'network_map.xml')
    for mac, uuid, role, adopted, online in (
        ('aabbccddee01', CONTROLLER, NodeRole.controller, True, True),
        ('aabbccddee02', ONLINE, NodeRole.node, False, True),
        ('aabbccddee03', OFFLINE, NodeRole.node, True, False),
    ):
        nodeconf.network_map[mac] = Node(
            uuid=uuid, mac=mac, name=f'{mac}._cuems_nodeconf._tcp.local.',
            node_role=role, ip='169.254.0.9', adopted=adopted, online=online,
        )
    nodeconf._save_network_map()
    nodeconf.communications_thread = MagicMock()
    return nodeconf


def _send(nodeconf, message):
    """Dispatch one request; return the reply engine_callback sent."""
    with patch('asyncio.run_coroutine_threadsafe'):
        nodeconf.engine_callback(message, MagicMock())
    return nodeconf.communications_thread.respond_to_engine.call_args[0][0]


def _on_disk(nodeconf):
    st = os.stat(nodeconf.map_path)
    with open(nodeconf.map_path, 'rb') as f:
        return f.read(), st.st_mtime_ns


def _alias_on_disk(nodeconf, mac):
    text = open(nodeconf.map_path).read()
    block = text[text.index(f'<mac>{mac}</mac>'):]
    block = block[:block.index('</node>')]
    if '<alias>' not in block:
        return None
    return block[block.index('<alias>') + 7:block.index('</alias>')]


class TestRefusals:
    """Section 3's refusal rows: exact text, and the file untouched."""

    @pytest.mark.parametrize('message, error', [
        ({'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'x', 'role_id': 'r', 'hostname': 'h'},
         'node_set accepts only alias; refused: hostname, role_id'),
        ({'action': 'node_set', 'node_uuid': ONLINE},
         'node_set needs an alias (null clears it)'),
        ({'action': 'node_set', 'alias': 'x'},
         'node_set needs a node uuid, got None'),
        ({'action': 'node_set', 'node_uuid': 7, 'alias': 'x'},
         'node_set needs a node uuid, got 7'),
        ({'action': 'node_set', 'node_uuid': ONLINE, 'alias': ''},
         'alias must be a non-empty string or null'),
        ({'action': 'node_set', 'node_uuid': ONLINE, 'alias': '   '},
         'alias must be a non-empty string or null'),
        ({'action': 'node_set', 'node_uuid': ONLINE, 'alias': 5},
         'alias must be a non-empty string or null'),
        ({'action': 'node_set', 'node_uuid': UNKNOWN, 'alias': 'x'},
         f'Node {UNKNOWN} not found'),
    ])
    def test_refused_with_exact_text_and_no_write(self, tmp_path, message, error):
        nodeconf = _nodeconf(tmp_path)
        before = _on_disk(nodeconf)
        time.sleep(0.01)

        assert _send(nodeconf, message) == {'OK': False, 'error': error}
        assert _on_disk(nodeconf) == before

    def test_before_ready_it_answers_the_feature_003_string(self, tmp_path):
        nodeconf = _nodeconf(tmp_path, ready=False)
        before = _on_disk(nodeconf)

        reply = _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'x'})

        assert reply == {'OK': False, 'error': 'nodeconf is still starting up'}
        assert _on_disk(nodeconf) == before

    def test_a_refused_blank_alias_does_not_poison_the_index(self, tmp_path):
        # R9: an in-place "" would make every later save fail on this row.
        nodeconf = _nodeconf(tmp_path)
        _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': ''})

        reply = _send(nodeconf, {'action': 'nodelist_modify', 'value': ONLINE, 'modify_action': 'ADD'})

        assert reply == {'OK': True}
        assert 'alias' not in nodeconf.network_map['aabbccddee02']
        assert nodeconf._map_write_pending is False

    def test_an_unknown_action_is_still_answered(self, tmp_path):
        reply = _send(_nodeconf(tmp_path), {'action': 'node_get'})
        assert reply == {'OK': False, 'error': 'unknown action: node_get'}


class TestSetClearUnchanged:

    def test_set_is_written_then_answered(self, tmp_path):
        nodeconf = _nodeconf(tmp_path)
        reply = _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'Stage left'})

        assert reply == {'OK': True}
        assert _alias_on_disk(nodeconf, 'aabbccddee02') == 'Stage left'

    def test_null_clears_it(self, tmp_path):
        nodeconf = _nodeconf(tmp_path)
        _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'Stage left'})

        reply = _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': None})

        assert reply == {'OK': True}
        assert _alias_on_disk(nodeconf, 'aabbccddee02') is None

    def test_the_same_value_again_is_ok_without_a_write(self, tmp_path):
        nodeconf = _nodeconf(tmp_path)
        _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'Stage left'})
        before = _on_disk(nodeconf)
        time.sleep(0.01)

        reply = _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'Stage left'})

        assert reply == {'OK': True}
        assert _on_disk(nodeconf) == before

    @pytest.mark.parametrize('mac, uuid', [('aabbccddee03', OFFLINE), ('aabbccddee01', CONTROLLER)])
    def test_an_offline_node_and_the_controller_can_be_labelled(self, tmp_path, mac, uuid):
        nodeconf = _nodeconf(tmp_path)
        assert _send(nodeconf, {'action': 'node_set', 'node_uuid': uuid, 'alias': 'L'}) == {'OK': True}
        assert _alias_on_disk(nodeconf, mac) == 'L'

    def test_a_failed_write_is_answered_and_owed_to_the_next_refresh(self, tmp_path):
        nodeconf = _nodeconf(tmp_path)
        with patch.object(CuemsNetworkMapType, 'save', side_effect=PermissionError('read-only')):
            reply = _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'L'})

        assert reply == {'OK': False, 'error': 'read-only'}
        assert nodeconf.network_map['aabbccddee02']['alias'] == 'L'
        assert nodeconf._map_write_pending is True


class TestTheLabelSurvives:

    def test_the_alias_is_on_the_object_the_document_serialises(self, tmp_path):
        nodeconf = _nodeconf(tmp_path)
        _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'L'})

        held = nodeconf.network_map['aabbccddee02']
        listed = [item['node'] for item in nodeconf._network_map_document()['node_list']]
        assert any(n is held for n in listed)

    def test_a_discovery_pass_that_changes_the_ip_keeps_the_alias_on_disk(self, tmp_path):
        # R4 — the reason the requirement exists: the next write is the daemon's.
        nodeconf = _nodeconf(tmp_path)
        _send(nodeconf, {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'Stage left'})
        nodeconf.listener.nodes['aabbccddee02'] = Node(
            uuid=ONLINE, mac='aabbccddee02', name='aabbccddee02._cuems_nodeconf._tcp.local.',
            node_role=NodeRole.node, ip='169.254.0.77', online=True,
        )

        nodeconf.refresh_network_map()

        text = open(nodeconf.map_path).read()
        assert '169.254.0.77' in text
        assert _alias_on_disk(nodeconf, 'aabbccddee02') == 'Stage left'


def test_dispatch_path_over_a_real_ipc_socket(tmp_path, monkeypatch):
    """Constitution IV: a Req0 client, the real AsyncCommsThread, a temp socket."""
    pynng = pytest.importorskip('pynng')
    from cuemsnodeconf import communicate

    socket_path = str(tmp_path / 'nodeconf.ipc')
    monkeypatch.setattr(communicate, 'NODECONF_IPC', socket_path)
    nodeconf = _nodeconf(tmp_path)
    thread = communicate.AsyncCommsThread(nodeconf.engine_callback)
    nodeconf.communications_thread = thread
    thread.start()
    try:
        for _ in range(100):
            if os.path.exists(socket_path):
                break
            time.sleep(0.02)
        with pynng.Req0(dial=f'ipc://{socket_path}', recv_timeout=5000) as client:
            client.send(json.dumps(
                {'action': 'node_set', 'node_uuid': ONLINE, 'alias': 'Over the wire'}).encode())
            reply = json.loads(client.recv().decode())
    finally:
        thread.stop()
        thread.join(timeout=5)

    assert reply == {'OK': True}
    assert _alias_on_disk(nodeconf, 'aabbccddee02') == 'Over the wire'
