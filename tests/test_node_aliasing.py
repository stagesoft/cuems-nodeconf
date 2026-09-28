"""T093 — the daemon's two links of the by-reference chain that keeps an adopt unlosable.

This daemon writes ``network_map.xml`` from two threads with no lock across
either path: ``_run_worker_loop`` merges discovery and rewrites the map every
30 s or on a debounced Avahi event, while ``adopt_node``/``unadopt_node`` mutate
and save from the comms thread. ``feat/nodelist-modify-hardening`` (``b53ee5f``)
added a ``threading.RLock`` on the grounds that a concurrent adopt could be lost.

Measured from ``cuems-utils`` on 2026-09-25, it cannot be: 60 trials running
both paths concurrently lose zero adoptions. The reason is **aliasing**, not
synchronisation — node dictionaries are passed by reference from the document
into the index, through ``merge``, and back, so an ``adopted`` flag set on the
index is *already* visible in the document about to be serialised. There is no
private copy for the write to be lost into.

That chain has four links and **nothing stated any of them**. Two are in
``cuemsutils`` and are pinned there by
``tests/contract/test_node_aliasing.py`` (its T091). The two below are this
daemon's, and they are this file:

  1. ``_index_from_document`` — the index holds the document's node objects
  2. ``_network_map_document`` — returns the *kept* document, refilled, never a copy

A ``dict(n)`` added to either for tidiness would reopen the window silently:
nothing here would fail, and neither would ``cuems-utils``' suite. Each test
below fails against a defensive-copy implementation of the link it covers.

Companion reading: ``cuems-utils``'
``specs/010-consumer-migration/nodeconf-map-write-divergence.md`` §4 for the
measurement, §7 for the task split, and its ``baseline.md`` for both repositories'
mutation runs.
"""

from unittest.mock import patch

from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node


def _nodeconf():
    """A daemon with start-up skipped — the same shape test_network_map.py uses."""
    nodeconf = CuemsNodeConf()
    nodeconf._document = CuemsNetworkMapType()
    nodeconf.network_map = NodeIndex()
    nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
    return nodeconf


def _a_node(mac='aabbccddeeff', node_uuid='u-1', adopted=False):
    return Node(
        uuid=node_uuid, mac=mac, name='n', node_role=NodeRole.node,
        ip='192.168.1.10', online=True, adopted=adopted,
    )


class TestTheIndexAliasesTheDocument:
    """Link 1 — ``_index_from_document`` must not copy."""

    def test_index_from_document_holds_the_documents_own_node_objects(self):
        """The identity assertion is the point.

        A value-only check passes against a copying implementation, because a
        copy still carries the right values. Only ``is`` distinguishes them.
        """
        nodeconf = _nodeconf()
        n = _a_node()
        nodeconf._document['node_list'] = [{'node': n}]

        index = nodeconf._index_from_document(nodeconf._document)

        assert index[n['mac']] is n, (
            '_index_from_document copied: an adopt made on the index would be '
            'invisible to the document the next write serialises'
        )


class TestTheDocumentIsKeptNotRebuilt:
    """Link 2 — ``_network_map_document`` returns the kept document, refilled."""

    def test_it_returns_the_kept_document_rather_than_a_new_one(self):
        nodeconf = _nodeconf()
        n = _a_node()
        nodeconf.network_map[n['mac']] = n

        document = nodeconf._network_map_document()

        assert document is nodeconf._document, (
            '_network_map_document built a new document; the daemon must never '
            'construct one (feature 002, FR-001/FR-002)'
        )

    def test_node_list_holds_the_indexs_own_node_objects(self):
        nodeconf = _nodeconf()
        n = _a_node()
        nodeconf.network_map[n['mac']] = n

        document = nodeconf._network_map_document()

        assert document['node_list'][0]['node'] is n, (
            'node_list holds a copy of the index\'s node'
        )


class TestTheAdoptRaceTheseLinksClose:
    """The property the two links exist to provide, in the harmful ordering."""

    def test_an_adopt_after_the_document_is_built_still_reaches_it(self):
        """The interleaving that actually loses an adoption if link 2 copies.

        The worker loop builds the document, THEN the comms thread adopts on the
        index, THEN the loop's refresh serialises. If ``_network_map_document``
        returned copies, the adoption would land on the index only and the write
        would drop it. Ordering matters here: adopting *before* the document is
        built survives a copy, so that arrangement proves nothing.
        """
        nodeconf = _nodeconf()
        n = _a_node(adopted=False)
        nodeconf._document['node_list'] = [{'node': n}]
        nodeconf.network_map = nodeconf._index_from_document(nodeconf._document)

        # worker loop: build the document for this pass
        document = nodeconf._network_map_document()
        # comms thread: adopt through the index only, touching no document
        assert nodeconf.network_map.adopt(n['uuid']) is True

        assert document['node_list'][0]['node']['adopted'] is True, (
            'the adoption did not reach the document this pass will serialise'
        )

    def test_the_same_holds_through_a_real_refresh(self):
        """End to end, with cuemsutils' refresh in the middle and the write stubbed."""
        nodeconf = _nodeconf()
        n = _a_node(adopted=False)
        nodeconf._document['node_list'] = [{'node': n}]
        nodeconf.network_map = nodeconf._index_from_document(nodeconf._document)
        nodeconf.listener.nodes[n['mac']] = dict(n)

        assert nodeconf.network_map.adopt(n['uuid']) is True
        with patch.object(CuemsNetworkMapType, 'save'):
            nodeconf.refresh_network_map()

        assert nodeconf.network_map[n['mac']]['adopted'] is True, (
            'a refresh pass discarded an adoption made on the index'
        )
