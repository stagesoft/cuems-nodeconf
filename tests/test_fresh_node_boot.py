"""The boot path a freshly installed node takes (feature 002, FR-004/FR-005, SC-005).

cuems-common ships `/etc/cuems/network_map.xml` with an empty `<node_list/>`, so
every fresh install boots against a map that does not list the node itself. Two
shapes matter, and neither was covered before this feature:

1. **The map is missing** — a development checkout, or a host where the file was
   deleted. The daemon seeds the shipped empty map, then loads it by the same
   path it uses for an existing map, so a document always exists.
2. **The map is the shipped empty one** — the real fresh-install case. Loading it
   must yield an empty index rather than raising, which depends on cuems-utils
   e363d03 (see tests/test_library_prerequisite.py).

The seed's mode is asserted, not assumed: a plain create is 0600 under umask
0077, this daemon runs as root, and the engines read the map as User=cuems
(constitution I).
"""
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
from cuemsnodeconf.CuemsAvahiListener import CuemsAvahiListener
from cuemsutils.config.network_map import CuemsNetworkMapType  # test-only (FR-007)
from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node

SHIPPED_EMPTY_MAP = (
    Path(__file__).resolve().parent / 'fixtures' / 'etc_cuems' / 'network_map_empty.xml'
)


def _nodeconf(map_path):
    nodeconf = CuemsNodeConf()
    nodeconf.network_map = NodeIndex()
    nodeconf.listener = CuemsAvahiListener(ip='169.254.1.1')
    nodeconf.map_path = str(map_path)
    return nodeconf


def _a_node():
    return Node(
        uuid='0367f391-ebf4-48b2-9f26-0000000000aa',
        mac='aabbccddeeff',
        name='aabbccddeeff._cuems_nodeconf._tcp.local.',
        node_role=NodeRole.node,
        ip='192.168.1.11',
        adopted=False,
        online=True,
    )


class TestSeedingAMissingMap:
    """No map on disk: write the shipped shape, then read it back."""

    def test_the_seed_is_byte_identical_to_the_shipped_map(self, cuems_conf_dir_empty):
        map_path = cuems_conf_dir_empty / 'network_map.xml'
        map_path.unlink()
        nodeconf = _nodeconf(map_path)

        nodeconf._seed_empty_map()

        assert map_path.read_bytes() == SHIPPED_EMPTY_MAP.read_bytes()

    def test_the_seed_is_readable_by_the_non_root_engine(self, cuems_conf_dir_empty):
        """Constitution I: root writes it, User=cuems reads it."""
        map_path = cuems_conf_dir_empty / 'network_map.xml'
        map_path.unlink()
        nodeconf = _nodeconf(map_path)

        previous = os.umask(0o077)  # the mode must not depend on the umask
        try:
            nodeconf._seed_empty_map()
        finally:
            os.umask(previous)

        assert stat.S_IMODE(map_path.stat().st_mode) == 0o644

    def test_seeding_leaves_no_temporary_behind(self, cuems_conf_dir_empty):
        """The write is atomic, so nothing partial survives it."""
        map_path = cuems_conf_dir_empty / 'network_map.xml'
        map_path.unlink()
        nodeconf = _nodeconf(map_path)

        nodeconf._seed_empty_map()

        assert sorted(p.name for p in cuems_conf_dir_empty.iterdir()) == [
            'network_map.xml', 'settings.xml',
        ]


class TestReadingTheShippedEmptyMap:
    """The real fresh-install case: the map exists and lists nobody."""

    def test_reads_as_an_empty_index_instead_of_raising(self, cuems_conf_dir_empty):
        nodeconf = _nodeconf(cuems_conf_dir_empty / 'network_map.xml')

        nodeconf.read_network_map()

        assert len(nodeconf.network_map) == 0

    def test_the_first_write_puts_this_node_in_the_map(self, cuems_conf_dir_empty):
        map_path = cuems_conf_dir_empty / 'network_map.xml'
        nodeconf = _nodeconf(map_path)
        nodeconf.read_network_map()

        nodeconf.network_map['aabbccddeeff'] = _a_node()
        nodeconf._save_network_map()

        reread = _nodeconf(map_path)
        reread.read_network_map()
        assert list(reread.network_map) == ['aabbccddeeff']


class TestRunSeedsExactlyOnce:
    """run()'s own branch — nothing else in the suite reaches it.

    Measured 2026-09-21: test_first_run_becomes_controller_scenario never calls
    run(), and test_run_exits_on_no_ip exits on the IP check before the map
    branch, so without this the seeding branch would ship untested.

    run() is stopped immediately after the map is read, at the first thing it
    does afterwards (Zeroconf), because everything past that point wants a
    network.
    """

    class _Stop(Exception):
        pass

    def test_run_seeds_a_missing_map_then_reads_it(self, cuems_conf_dir_empty):
        map_path = cuems_conf_dir_empty / 'network_map.xml'
        map_path.unlink()
        nodeconf = _nodeconf(map_path)

        def _set_ip():
            nodeconf.ip = '169.254.1.1'

        with patch.object(nodeconf, 'get_ips', side_effect=_set_ip), \
             patch('cuemsnodeconf.CuemsNodeConf.Zeroconf', side_effect=self._Stop):
            with pytest.raises(self._Stop):
                nodeconf.run()

        assert map_path.read_bytes() == SHIPPED_EMPTY_MAP.read_bytes()
        assert len(nodeconf.network_map) == 0

    def test_run_does_not_overwrite_a_map_that_exists(self, cuems_conf_dir):
        """The seed must never discard a live topology."""
        map_path = cuems_conf_dir / 'network_map.xml'
        before = map_path.read_bytes()
        nodeconf = _nodeconf(map_path)

        def _set_ip():
            nodeconf.ip = '169.254.1.1'

        with patch.object(nodeconf, 'get_ips', side_effect=_set_ip), \
             patch('cuemsnodeconf.CuemsNodeConf.Zeroconf', side_effect=self._Stop):
            with pytest.raises(self._Stop):
                nodeconf.run()

        assert map_path.read_bytes() == before
