# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
import netifaces
import time
import os.path
import sys
import socket
import threading
import systemd.daemon
import dbus
import shutil

from zeroconf import IPVersion, ServiceInfo, ServiceListener, ServiceBrowser, Zeroconf, ZeroconfServiceTypes

from .CuemsAvahiListener import CuemsAvahiListener
from .CuemsNode import CuemsNode, CuemsNodeDict
from . import NodeXmlBuilders  # Register custom XML builders for node_list and node

from cuemsutils.xml.XmlReaderWriter import XmlReader, XmlWriter
from cuemsutils.timeoutloop import Timeoutloop
from cuemsutils.log import Logger, logged
from cuemsutils.helpers import strtobool
from .communicate import AsyncCommsThread, TIMEOUT
import asyncio


CUEMS_CONF_PATH = '/etc/cuems/'
MAP_SCHEMA_FILE = 'network_map.xsd'
MAP_FILE = 'network_map.xml'
TEMPLATES_PATH = '/usr/share/cuems/'
CUEMS_SERVICE_FILE = 'cuems.service'
CUEMS_MASTER_LOCK_FILE = 'master.lock'
CONTROLLER_INTERFACES_TEMPLATE = 'interfaces.master'
NODE_INTERFACES_TEMPLATE = 'interfaces.node'

MASTER_ALIAS='controller.local'
CONTROLLER_ALIAS='formitgo.local'


class CuemsNodeConf():

    def __init__(self):
        self.xsd_path = os.path.join( CUEMS_CONF_PATH, MAP_SCHEMA_FILE)
        self.map_path = os.path.join( CUEMS_CONF_PATH, MAP_FILE)
        self.network_map = CuemsNodeDict()
        # Decided in run() from the presence of network_map.xml; default so
        # the merge helpers can run on an instance that never called run().
        self.is_first_run = False

        self.services = ['_cuems_nodeconf._tcp.local.']

        # Daemon lifecycle / long-running state.
        self.running = False
        self.stop_requested = False
        # Set by avahi discovery callbacks; the worker loop wakes on it.
        self._dirty = threading.Event()
        # Signature of the last map we wrote, so we only rewrite /etc on change.
        self._last_map_sig = None
        # Serializes mutate+write of self.network_map. THREE places touch it:
        # run()'s startup load, the main worker loop (avahi events / the 30 s
        # tick) and the comms thread (adopt/unadopt over /tmp/nodeconf.ipc).
        # The last two render through the SAME temp path (map.tmp.<pid>) before
        # os.replace, so without this lock two concurrent writers can clobber
        # that file and promote a truncated map that neither the engine nor the
        # editor can load. The startup load never writes, but it does REPLACE
        # the dict while the comms thread may already be iterating it.
        self._map_lock = threading.RLock()
        # Lazily-created collaborators (so stop() can tear them down safely).
        self.communications_thread = None
        self.zeroconf = None
        self.browser = None
        self.listener = None
        self.alias_publisher = None
        self.ip = None
        self.controller_ip = None
        # Real interface names backing self.ip / self.controller_ip, captured by
        # get_ips() so alias publication can be scoped to the right interface.
        self.cluster_iface = None
        self.ui_iface = None

    def stop(self):
        """Tear down the daemon cleanly (called from the signal handler)."""
        Logger.info('Stopping CuemsNodeConf')
        self.stop_requested = True
        self.running = False
        # Wake the worker loop so it observes stop_requested and returns.
        self._dirty.set()
        if self.alias_publisher is not None:
            try:
                self.alias_publisher.close()
            except Exception as e:
                Logger.warning(f'Error closing alias publisher: {e}')
        if self.browser is not None:
            try:
                self.browser.cancel()
            except Exception as e:
                Logger.warning(f'Error cancelling service browser: {e}')
        if self.zeroconf is not None:
            try:
                self.zeroconf.close()
            except Exception as e:
                Logger.warning(f'Error closing zeroconf: {e}')
        if self.communications_thread is not None:
            try:
                self.communications_thread.stop()
            except Exception as e:
                Logger.warning(f'Error stopping comms thread: {e}')

    def start(self):
        Logger.debug('Starting CuemsNodeConf')
        self.set_comms()
        self.run()


    def set_comms(self):
        Logger.info('Setting up Communicators')
        self.communications_thread = AsyncCommsThread(self.engine_callback)
        self.communications_thread.start()

    def engine_callback(self, message, context):
        """Handle one request from the engine over /tmp/nodeconf.ipc.

        EVERY path must answer. This is an NNG Req/Rep socket: a request we
        return from without responding leaves the engine blocked until its own
        15 s timeout, which surfaces to the operator as an unexplained stall.
        Before the else-branch below, any well-formed message carrying an action
        other than 'nodelist_modify' fell off the end of the if and did exactly
        that.
        """
        try:
            action = message.get('action')
            if action == 'nodelist_modify':
                node_uuid = message.get('value')
                modify_action = message.get('modify_action')
                
                if modify_action == 'ADD':
                    result = self.adopt_node(node_uuid)
                elif modify_action == 'REMOVE':
                    result = self.unadopt_node(node_uuid)
                else:
                    result = {'OK': False, 'error': f'Invalid modify_action: {modify_action}'}
                
                response = {'OK': result.get('OK', False)}
                if 'error' in result:
                    response['error'] = result['error']
                
                asyncio.run_coroutine_threadsafe(
                    self.communications_thread.respond_to_engine(response, context),
                    self.communications_thread.event_loop
                )
                return

            Logger.warning(f'Unknown action from engine: {action!r}')
            asyncio.run_coroutine_threadsafe(
                self.communications_thread.respond_to_engine(
                    {'OK': False, 'error': f'unknown action: {action}'}, context
                ),
                self.communications_thread.event_loop
            )
            return
        except Exception as e:
            Logger.error(f'Error in engine_callback: {e}')
            Logger.exception(e)
            error_response = {'OK': False, 'error': str(e)}
            asyncio.run_coroutine_threadsafe(
                self.communications_thread.respond_to_engine(error_response, context),
                self.communications_thread.event_loop
            )

    def run(self):
        Logger.debug('Running CuemsNodeConf')
        try:
            self.get_ips()
        except TimeoutError:
            Logger.critical('Could not find network interfaces within timeout')
            sys.exit(-1)
        
        # Validate that IP was obtained
        if self.ip is None:
            Logger.critical('Failed to obtain network IP address. Cannot continue.')
            sys.exit(-1)

        # Under _map_lock: set_comms() ran before us (see start()), so the
        # comms thread is ALREADY accepting adopt/unadopt requests while we
        # replace the map here. Startup is not instant either — a master sleeps
        # 5 s for slaves to appear and may wait up to 30 s on firstrun nodes —
        # so this window is wide enough for a UI click to land inside it and
        # iterate a dict we are in the middle of replacing.
        with self._map_lock:
            self.is_first_run = not os.path.isfile(self.map_path)
            if not self.is_first_run:
                Logger.debug('Reading existing network_map.xml')
                self.read_network_map()
            else:
                Logger.debug('No existing network_map.xml found, starting fresh')
                self.network_map = CuemsNodeDict()

        self.zeroconf = Zeroconf(interfaces=[self.ip],ip_version=IPVersion.V4Only)

        self.start_avahi_listener()
        
        # Wait for local service to be registered and discovered
        Logger.debug('Waiting for local service registration...')
        try:
            self.wait_for_local_service_registration()
        except TimeoutError:
            Logger.critical('Local service did not register within timeout period')
            sys.exit(-1)
        
        try:
            self.node = self.retreive_local_node()
        except TimeoutError:
            Logger.critical('Could not find local node on the network')
            sys.exit(-1)

        # Check for first run flag in service file
        if self.node.node_type == CuemsNode.NodeType.firstrun:
            if self._should_resume_master():
                # This host was the controller before (master.lock present, or
                # the existing network_map already records this node as master).
                # Resume that role instead of re-running the firstrun election.
                # We only reinstate the avahi service template here; the network
                # is assumed already in master configuration (do NOT restart
                # networking on a resume — that is disruptive and unnecessary).
                Logger.info('Resuming master role from existing state (skipping firstrun election)')
                self.node.node_type = CuemsNode.NodeType.master
                self._install_master_service_template()
            else:
                Logger.debug("First time conf file detected, triying to autoconfigure node")
                self.set_node_type()
        else:
            Logger.debug(f"Allready configured as {self.node.node_type.name}")
        
        # If I am master, give slaves a moment to appear before the first pass.
        if self.node.node_type == CuemsNode.NodeType.master:
            time.sleep(5)
        self.publish_aliases_if_master()

        if self.listener.nodes.firstruns:
            Logger.debug('Waiting for some other "first-run" nodes')
        # Add timeout to prevent infinite loop
        max_iterations = 60  # 30 seconds max (60 * 0.5)
        iteration = 0
        while self.listener.nodes.firstruns and iteration < max_iterations:
            time.sleep(0.5)
            iteration += 1
        if iteration >= max_iterations and self.listener.nodes.firstruns:
            Logger.warning('Timeout waiting for firstrun nodes to resolve. Continuing anyway.')

        self.check_nodes()
        self.refresh_network_map()
        self.update_master_lock_file(os.path.join( CUEMS_CONF_PATH, CUEMS_MASTER_LOCK_FILE))

        # Initial discovery pass complete: tell systemd we're up, then stay
        # resident reacting to avahi events. The old one-shot daemon exited
        # here, which is why <ip>/<online> went stale and the aliases were
        # unsupervised after boot.
        self.notify_systemd()
        self._run_worker_loop()

    def refresh_network_map(self):
        """Merge discovery into the map; write to /etc only if content changed.

        Runs on the main worker thread. The whole mutate+write is under
        _map_lock because adopt_node/unadopt_node do the same from the comms
        thread — see __init__ for why sharing the temp path matters.
        """
        with self._map_lock:
            self.merge_discovered_nodes()
            self.set_master_always_adopted()
            self.check_missing_adopted_nodes()
            sig = self._map_signature(self.network_map)
            if sig == self._last_map_sig:
                Logger.debug('network_map unchanged; skipping write')
                return
            try:
                self.write_network_map(self.network_map)
                self._last_map_sig = sig
            except PermissionError as e:
                Logger.error(f"Permission denied writing network map to {self.map_path}: {e}")
                Logger.exception(e)
            except Exception as e:
                Logger.error(f"Error writing network map: {type(e).__name__}: {e}")
                Logger.exception(e)

    def _run_worker_loop(self):
        """Resident loop: on each (debounced) avahi event or every 30 s, refresh
        the map and re-ensure the master aliases. Node arrivals/departures and
        IPv4LL address renegotiation self-heal without a daemon restart."""
        self.running = True
        Logger.info('nodeconf entering resident discovery loop')
        while self.running and not self.stop_requested:
            triggered = self._dirty.wait(timeout=30)
            if self.stop_requested or not self.running:
                break
            self._dirty.clear()
            if triggered:
                time.sleep(2)        # coalesce a burst of avahi events
                self._dirty.clear()
            try:
                self.get_ips()
            except TimeoutError:
                Logger.warning('get_ips timed out in resident loop; retrying next tick')
                continue
            try:
                self.refresh_network_map()
                self.publish_aliases_if_master()
            except Exception as e:
                Logger.error(f'Error in nodeconf worker loop: {type(e).__name__}: {e}')
                Logger.exception(e)
        Logger.info('nodeconf worker loop exited')

    def on_node_event(self, caller_node=None, action=None):
        """Avahi discovery callback (add/update/remove). Flags the worker loop;
        the actual merge/write happens there, debounced."""
        Logger.debug(f'avahi event: action={action} node={caller_node}')
        self._dirty.set()

    def _map_signature(self, nmap):
        """Stable signature of the persisted fields, to detect real changes."""
        sig = []
        for mac in sorted(nmap.keys()):
            node = nmap[mac]
            nt = node.get('node_type')
            nt = nt.name if hasattr(nt, 'name') else str(nt)
            sig.append((
                mac, node.get('uuid'), nt, node.get('ip'),
                bool(node.get('adopted', False)), bool(node.get('online', False)),
                node.get('role_id'), node.get('alias'), node.get('hostname'),
            ))
        return tuple(sig)

    def notify_systemd(self, status='READY=1'):

        Logger.debug('Startup complete, notifying systemd')
        systemd.daemon.notify(status)
    # Cluster-link candidates, in order. The ':avahi' labels are where
    # avahi-autoipd puts an IPv4LL address; a cluster link configured with a
    # STATIC 169.254.x address (e.g. `address 169.254.0.1/16` in
    # /etc/network/interfaces, so ProxyJump addresses never move) has no such
    # label, so the plain interface is accepted too -- but only for a
    # link-local address, never the AP bridge's 192.168.6.1 or a LAN address.
    CLUSTER_LINK_LABELS = (('bridge0', 'bridge0:avahi'), ('ethernet1', 'ethernet1:avahi'))

    @staticmethod
    def _ipv4_of(name):
        try:
            return [a['addr'] for a in netifaces.ifaddresses(name).get(netifaces.AF_INET, []) if a.get('addr')]
        except (ValueError, KeyError):
            return []

    def _cluster_address(self):
        """(ip, real_iface) of the cluster link, or (None, None).

        Prefers avahi-autoipd's labelled address (unchanged behaviour), then a
        static link-local address on the same interface."""
        for iface, label in self.CLUSTER_LINK_LABELS:
            addrs = self._ipv4_of(label)
            if addrs:
                Logger.debug(f"Found {label} interface, IP: {addrs[0]}")
                return addrs[0], iface
        for iface, _label in self.CLUSTER_LINK_LABELS:
            for addr in self._ipv4_of(iface):
                if addr.startswith('169.254.'):
                    Logger.debug(f"No {iface}:avahi label; using static link-local {addr} on {iface}")
                    return addr, iface
        return None, None

    def get_ips(self):
        # self.ip            = cluster/node-side address (publishes controller.local)
        # self.controller_ip = UI/outward address (publishes the UI alias)
        # cluster_iface/ui_iface record the REAL interface backing each address
        # so alias publication can be scoped to a single interface (avahi static
        # records otherwise flood every interface — the macOS .local trap).
        self.ip = None
        self.controller_ip = None
        self.cluster_iface = None
        self.ui_iface = None
        for passed in Timeoutloop(timeout=10, interval=1):
            self.ip, self.cluster_iface = self._cluster_address()
            if self.cluster_iface == 'bridge0':
                # A node: the bridge is its only cluster-side interface.
                return
            if self.ip is None:
                Logger.debug("Waiting for the cluster link (bridge0/ethernet1) to get an address")
            try:
                self.controller_ip = netifaces.ifaddresses('bond0')[netifaces.AF_INET][0]['addr']
                self.ui_iface = 'bond0'
                if self.ip != None:
                    Logger.debug(f"Found bond0 interface, CONTROLLER IP: {self.controller_ip}")
                    return
                else:
                    Logger.debug(f"Found bond0 interface, but the cluster link has no address yet, continuing")
            except (ValueError, KeyError):
                Logger.debug("Waiting for bond0 interface to appear")

    def start_avahi_listener(self):
        self.listener = CuemsAvahiListener(ip=self.ip, callback=self.on_node_event)
        self.browser = ServiceBrowser(
            self.zeroconf, self.services, self.listener)

    def _should_resume_master(self):
        """True if this host was the controller before, so a firstrun election
        should be skipped and the master role resumed.

        Signals (either suffices):
          - /etc/cuems/master.lock present (this host last ran as controller), or
          - the existing network_map already records THIS node (by mac) as master.
        """
        lock_path = os.path.join(CUEMS_CONF_PATH, CUEMS_MASTER_LOCK_FILE)
        if os.path.isfile(lock_path):
            Logger.debug('master.lock present -> resume master')
            return True
        try:
            own = self.network_map.get(self.node.mac)
            if own is not None and own.node_type == CuemsNode.NodeType.master:
                Logger.debug('existing network_map records this node as master -> resume master')
                return True
        except Exception:
            pass
        return False

    def _install_master_service_template(self):
        """Copy the master avahi service template into place (idempotent)."""
        source = os.path.join(TEMPLATES_PATH, CUEMS_SERVICE_FILE) + '.master'
        target = os.path.join('/etc/avahi/services/', CUEMS_SERVICE_FILE)
        try:
            shutil.copy2(source, target)
        except FileNotFoundError:
            Logger.error(f"Master service template not found at {source}")
            raise
        except PermissionError:
            Logger.error(f"Permission denied copying service template to {target}")
            raise
        except Exception as e:
            Logger.error(f"Error copying master service template: {type(e).__name__}: {e}")
            Logger.exception(e)
            raise

    def set_node_type(self):
        if not self.listener.nodes.masters:
            Logger.debug('No master node on the network, I become MASTER!')
            self.node.node_type = CuemsNode.NodeType.master

            self._install_master_service_template()

            if not self.change_network_to_master():
                Logger.error("Failed to change network to master configuration")
                raise RuntimeError("Network configuration change failed")
            
            try:
                self.get_ips()
            except TimeoutError:
                Logger.error("Failed to get IP addresses after network change")
                raise
        else:
            Logger.debug('Master present on the in network WE STAY SLAVE')
            self.node.node_type = CuemsNode.NodeType.slave

            # Copy slave node service template. nodeconf runs as root, so a
            # direct copy is correct here — the old `sudo cp` shelled out
            # needlessly and silently fails when sudo isn't passwordless.
            source = os.path.join(TEMPLATES_PATH, CUEMS_SERVICE_FILE) + '.slave'
            target = os.path.join('/etc/avahi/services/', CUEMS_SERVICE_FILE)
            try:
                shutil.copy2(source, target)
            except FileNotFoundError:
                Logger.error(f"Slave service template not found at {source}")
                raise
            except Exception as e:
                Logger.error(f"Error copying slave service template: {type(e).__name__}: {e}")
                Logger.exception(e)
                raise
        
    def write_network_map(self, map=None):
        if not map:
            map = self.network_map if hasattr(self, 'network_map') and self.network_map else self.listener.nodes

        # Build a SEPARATE serialization map. We must not mutate the live nodes:
        # converting node_type enum -> str in place broke later enum comparisons
        # (set_master_always_adopted / unadopt_node's master guard) after the
        # first write. Unknown-to-nodeconf fields (role_id, alias, hostname set
        # by operators) are copied through verbatim so a rewrite never drops them.
        required_fields = ['uuid', 'mac', 'name', 'node_type', 'ip']
        serializable = CuemsNodeDict()
        for mac, node in map.items():
            for field in required_fields:
                if node.get(field) is None:
                    Logger.error(f"Node {mac} has None value for required field '{field}'. Node data: {dict(node)}")
                    raise ValueError(f"Cannot write network map: Node {mac} has None value for required field '{field}'")

            snode = CuemsNode(dict(node))  # shallow copy; live node untouched

            # node_type -> "NodeType.<name>" string for cuems-engine compatibility.
            nt = snode.get('node_type')
            if hasattr(nt, 'name'):
                snode['node_type'] = f"NodeType.{nt.name}"

            # Normalize adopted/online to bool (XmlWriter renders BoolType).
            for boolfield in ('adopted', 'online'):
                val = snode.get(boolfield)
                if val is None:
                    snode[boolfield] = False
                elif isinstance(val, str):
                    try:
                        snode[boolfield] = strtobool(val)
                    except ValueError:
                        snode[boolfield] = False

            serializable[mac] = snode

        # Atomic write: render to a temp file in the same dir, then os.replace
        # so a concurrent reader (engine/editor at restart) never sees a
        # half-written map.
        tmp_path = f"{self.map_path}.tmp.{os.getpid()}"
        writer = XmlWriter(schema_name = self.xsd_path, xmlfile = tmp_path, xml_root_tag='CuemsNetworkMap')
        writer.write_from_object(serializable)
        os.replace(tmp_path, self.map_path)
        Logger.debug("Network map written to XML (atomic)")

    def _cluster_master_uuids(self):
        """UUIDs of the controller(s) this host belongs to.

        These are the ONLY masters allowed in this host's network_map. Several
        CUEMS clusters routinely share one LAN (the taller has test2, test and
        test3 side by side), and every controller advertises itself as a
        master over mDNS. Without this filter a controller's nodeconf merged
        every peer controller it heard into its own map and
        set_master_always_adopted() then marked them ADOPTED, so the engine
        counted foreign controllers as members of this cluster.

        - A controller is its own cluster's master.
        - A node's master is whatever master its map already records (set when
          it joined). On a map with no master yet (fresh node, or legacy map)
          the set is empty and the first discovered master is accepted, as
          before.
        """
        own = getattr(self, 'node', None)
        if (own is not None
                and own.node_type == CuemsNode.NodeType.master
                and own.get('uuid')):
            return {own.uuid}
        return {
            n.uuid for n in self.network_map.values()
            if n.node_type == CuemsNode.NodeType.master and n.get('uuid')
        }

    @staticmethod
    def _is_foreign_master(node, cluster_masters):
        """A master that is not one of ours — another cluster's controller."""
        return (
            node.node_type == CuemsNode.NodeType.master
            and bool(cluster_masters)
            and node.get('uuid') not in cluster_masters
        )

    def merge_discovered_nodes(self):
        Logger.debug('Merging discovered nodes with network_map')
        cluster_masters = self._cluster_master_uuids()
        # Match discovered nodes to the existing map by UUID, the stable primary
        # key (per the node-identity model). We must NOT key on the mac derived
        # from the avahi service name: the controller advertises its service as
        # 'controller' (so peers resolve controller.local), not its MAC, so
        # get_mac() yields a garbage key ('controller._'). Keying merges on that
        # created a DUPLICATE controller node every discovery pass and flipped
        # the real (mac-keyed) entry to online=False, orphaning the operator
        # fields role_id/alias/hostname.
        existing_by_uuid = {
            node.get('uuid'): (mac, node)
            for mac, node in self.network_map.items()
            if node.get('uuid')
        }

        discovered_uuids = set()
        for _disc_key, discovered_node in self.listener.nodes.items():
            d_uuid = discovered_node.get('uuid')
            if self._is_foreign_master(discovered_node, cluster_masters):
                # Another cluster's controller on the shared LAN: not ours,
                # never enters this map (see _cluster_master_uuids).
                Logger.debug(
                    f'Ignoring foreign controller {discovered_node.get("name")} '
                    f'(uuid={d_uuid}, ip={discovered_node.get("ip")}): '
                    f'not this cluster\'s master'
                )
                continue
            if d_uuid:
                discovered_uuids.add(d_uuid)

            match = existing_by_uuid.get(d_uuid)
            if match is not None:
                mac, existing_node = match
                preserved_adopted = existing_node.adopted
                # Refresh mutable discovery fields (ip, name, node_type) in
                # place but keep the real mac key and the operator fields; never
                # clobber the real mac with the name-parse.
                existing_node.update(
                    {k: v for k, v in discovered_node.items() if k != 'mac'}
                )
                existing_node.adopted = preserved_adopted
                existing_node.online = True
                Logger.debug(f'Merged discovered uuid={d_uuid} into existing node {mac}, preserved adopted={preserved_adopted}')
            else:
                # Genuinely new node. Real slaves name their service by MAC, so
                # the discovered key is the real mac here.
                key = discovered_node.get('mac')
                self.network_map[key] = discovered_node
                self.network_map[key].adopted = False
                self.network_map[key].online = True
                Logger.debug(f'Added new discovered node uuid={d_uuid} key={key}')

        # Purge foreign controllers that an earlier (unfiltered) pass already
        # persisted — e.g. a peer controller recorded as adopted=True.
        for mac in [m for m, n in self.network_map.items()
                    if self._is_foreign_master(n, cluster_masters)]:
            gone = self.network_map.pop(mac)
            Logger.info(
                f'Dropped foreign controller {gone.get("name")} '
                f'(uuid={gone.get("uuid")}, ip={gone.get("ip")}) from '
                f'network_map: it belongs to another cluster'
            )

        # Offline pass keyed on UUID, not mac (same reason as above).
        for mac, node in self.network_map.items():
            if node.get('uuid') not in discovered_uuids:
                node.online = False
                Logger.debug(f'Node {mac} (uuid={node.get("uuid")}) is offline')

    def set_master_always_adopted(self):
        for mac, node in self.network_map.items():
            if node.node_type == CuemsNode.NodeType.master:
                node.adopted = True
                Logger.debug(f'Set master node {mac} as always adopted')
        
        if self.is_first_run:
            for mac, node in self.network_map.items():
                if node.node_type != CuemsNode.NodeType.master:
                    node.adopted = False

    def check_missing_adopted_nodes(self):
        adopted_nodes = [node for node in self.network_map.values() if node.adopted]
        discovered_uuids = {node.uuid for node in self.listener.nodes.values()}
        
        missing_adopted = []
        for node in adopted_nodes:
            if node.uuid not in discovered_uuids:
                missing_adopted.append(node)
        
        if missing_adopted:
            Logger.warning(f'Missing adopted nodes: {[f"{n.name} ({n.uuid})" for n in missing_adopted]}')
        else:
            Logger.debug('All adopted nodes are present')

    def adopt_node(self, node_uuid):
        """Mark a node adopted and persist the map. Called from the comms thread.

        Under _map_lock: the worker loop mutates and writes the same map from
        the main thread.
        """
        with self._map_lock:
            for node in self.network_map.values():
                if node.uuid == node_uuid:
                    # Check if node is already adopted
                    if node.adopted:
                        Logger.debug(f'Node {node_uuid} is already adopted')
                        return {'OK': True, 'message': 'Node already adopted'}

                    # Check if node is online
                    if not node.online:
                        Logger.warning(f'Cannot adopt node {node_uuid}: node is offline')
                        return {'OK': False, 'error': f'Cannot adopt node {node_uuid}: node is offline'}

                    node.adopted = True
                    self.write_network_map(self.network_map)
                    # Keep the worker loop's change-detection in step with what
                    # we just wrote, so its next tick doesn't rewrite identical
                    # content.
                    self._last_map_sig = self._map_signature(self.network_map)
                    Logger.info(f'Node {node_uuid} adopted')
                    return {'OK': True}

            Logger.warning(f'Node {node_uuid} not found in network_map')
            return {'OK': False, 'error': f'Node {node_uuid} not found'}

    def unadopt_node(self, node_uuid):
        """Drop a node's adoption and persist the map (comms thread).

        Under _map_lock, same reason as adopt_node.
        """
        with self._map_lock:
            for node in self.network_map.values():
                if node.uuid == node_uuid:
                    if node.node_type == CuemsNode.NodeType.master:
                        Logger.warning(f'Cannot unadopt master node {node_uuid}')
                        return {'OK': False, 'error': 'Cannot unadopt master node'}

                    # Check if node is already unadopted
                    if not node.adopted:
                        Logger.debug(f'Node {node_uuid} is already unadopted')
                        return {'OK': True, 'message': 'Node already unadopted'}

                    # Note: Offline nodes can and should be unadoptable
                    # This allows cleaning up nodes that have gone offline
                    if not node.online:
                        Logger.info(f'Unadopting offline node {node_uuid} (node is not online)')

                    node.adopted = False
                    self.write_network_map(self.network_map)
                    self._last_map_sig = self._map_signature(self.network_map)
                    Logger.info(f'Node {node_uuid} unadopted')
                    return {'OK': True}

            Logger.warning(f'Node {node_uuid} not found in network_map')
            return {'OK': False, 'error': f'Node {node_uuid} not found'}

    def read_network_map(self):
        reader = XmlReader(schema_name = self.xsd_path, xmlfile = self.map_path)
        self.network_map = CuemsNodeDict()
        nodes = reader.read_to_objects()
        for node in nodes:
            # Normalize node_type - handle both "master" and "NodeType.master" formats
            if 'node_type' in node:
                node_type_str = str(node['node_type'])
                # Remove "NodeType." prefix if present
                if node_type_str.startswith('NodeType.'):
                    node_type_str = node_type_str.replace('NodeType.', '')
                # Convert to enum
                try:
                    node['node_type'] = CuemsNode.NodeType[node_type_str]
                except KeyError:
                    Logger.error(f"Invalid node_type '{node_type_str}' for node {node.get('mac', 'unknown')}")
                    # Default to slave if invalid
                    node['node_type'] = CuemsNode.NodeType.slave
            
            # Note: Boolean fields are already parsed by CuemsParser using strtobool
            # No additional conversion needed - they come as Python bool from read_to_objects()
            
            self.network_map[node.mac] = node
        
        Logger.debug("---")
        Logger.debug("Nodes read from existing XML network map:")
        for item, value in self.network_map.items():
            Logger.debug(f"{value}")
        Logger.debug("---")

    def cleanup(self):
        try:
            os.remove(os.path.join(CUEMS_CONF_PATH, self.cm.show_lock_file))
        except FileNotFoundError:
            pass

    def callback(self, caller_node=None, action=CuemsAvahiListener.Action.ADD):
        Logger.debug(f" {action} callback!!!, Node: {caller_node} ")

        self.check_nodes()

    def check_nodes(self):
        # Logger.debug(self.listener.nodes)
        if self.listener.nodes.masters:
            Logger.debug(f"Master node(s):\n{self.listener.nodes.masters}")
        else:
            Logger.debug(f"We have no MASTER!! yet? waiting for it")
        if self.listener.nodes.slaves:
            Logger.debug(
                f"We have {len(self.listener.nodes.slaves)} slaves")
            Logger.debug(f"Slave node(s):\n{self.listener.nodes.slaves}")
        else:
            Logger.debug("we have no slaves")

    def check_first_run(self):
        for node in self.listener.nodes.firstruns:
            if node.ip == self.ip:
                return True

        return False
    
    def wait_for_local_service_registration(self):
        """
        Wait for the local service to be registered and discovered by the Avahi listener.
        This ensures the service is available before we try to retrieve it.
        """
        for passed in Timeoutloop(timeout=5, interval=0.2):
            for node in self.listener.nodes.values():
                if node.ip == self.ip:
                    Logger.debug(f'Local service registered and discovered: {node.name}')
                    return
            
            Logger.debug("Waiting for local service to be registered...")
        
        # Timeout occurred - Timeoutloop will raise TimeoutError
        raise TimeoutError('Local service registration not detected within timeout period')

    def retreive_local_node(self):
        for passed in Timeoutloop(timeout=10, interval=1):
            for node in self.listener.nodes.values():
                if node.ip == self.ip:
                    return node

            Logger.debug("waiting for local node to appear on the network")
        
        # Timeout occurred - Timeoutloop will raise TimeoutError
        raise TimeoutError('Local node not found within timeout period')
        

    def _ui_alias(self):
        """The outward/UI-facing mDNS alias (published on bond0).

        Deployment constant for now (CONTROLLER_ALIAS). It is intentionally a
        real .local name (e.g. formitgo.local), distinct from the free-form
        operator <alias> map field. Returns None to skip publication.
        """
        return CONTROLLER_ALIAS or None

    def publish_aliases_if_master(self):
        """Ensure the master's avahi aliases are published, interface-scoped.

        - controller.local -> cluster interface (self.ip). SKIPPED when the OS
          hostname is exactly 'controller': avahi already publishes
          <hostname>.local per-interface-correctly, so a static record is
          redundant and risks a duplicate/unreachable A answer (the macOS
          .local trap). When the hostname is prefixed (cluster.conf), the name
          is NOT auto-published, so nodeconf must.
        - UI alias -> outward interface (self.controller_ip).

        Both use avahi's D-Bus EntryGroup.AddAddress with an explicit interface
        index (AliasPublisher), which — unlike `avahi-publish -a` — does not
        flood the record onto every interface.
        """
        node = getattr(self, 'node', None)
        if node is None or node.node_type != CuemsNode.NodeType.master:
            return

        if self.alias_publisher is None:
            from .AliasPublisher import AliasPublisher
            self.alias_publisher = AliasPublisher()

        if socket.gethostname() != 'controller':
            if self.ip and self.cluster_iface:
                self.alias_publisher.ensure(MASTER_ALIAS, self.ip, self.cluster_iface)
            else:
                Logger.warning(f"Cannot publish {MASTER_ALIAS}: cluster ip/iface unknown")
        else:
            Logger.debug(f"hostname is 'controller'; native avahi already serves {MASTER_ALIAS}")

        ui_alias = self._ui_alias()
        if ui_alias:
            if self.controller_ip and self.ui_iface:
                self.alias_publisher.ensure(ui_alias, self.controller_ip, self.ui_iface)
            else:
                Logger.debug(f"Cannot publish {ui_alias}: UI ip/iface not present (no outward interface?)")
        else:
            Logger.debug('No UI alias configured; skipping UI alias publication')

    def update_master_lock_file(self, path):
        if self.node.node_type == CuemsNode.NodeType.master:
            if  not os.path.isfile(path):
                try:
                    with open(path, 'a') as results_file:
                        results_file.write('\n')
                    Logger.debug("Created new master file")
                except:
                    Logger.warning("could not write master lock file")
        else:
            if os.path.isfile(path):
                try:
                    os.remove(path)
                    Logger.debug("Removed master file")
                except OSError:
                    Logger.warning("could not delete master lock file")
    
    def change_network_to_master(self):
        try:
            sysbus = dbus.SystemBus()
            systemd1 = sysbus.get_object('org.freedesktop.systemd1', '/org/freedesktop/systemd1')
            manager = dbus.Interface(systemd1, 'org.freedesktop.systemd1.Manager')
            
            job = manager.StopUnit('networking.service', 'fail')
            Logger.debug("Stopping networking service")
            time.sleep(10)
            
            try:
                self.change_network_settings_to_master()
            except Exception as e:
                Logger.error(f"Error changing network settings: {e}")
                Logger.exception(e)
                return False
            
            job = manager.StartUnit('networking.service', 'fail')
            Logger.debug("Starting networking service")
            time.sleep(10)
            Logger.debug("Networking service restarted successfully")
            
            try:
                job = manager.StartUnit('avahi-daemon.service', 'fail')
                time.sleep(10)
                Logger.debug("Avahi daemon restarted successfully, continuing")
            except Exception as e:
                Logger.warning(f"Error restarting avahi-daemon service: {e}")
                Logger.exception(e)
                # Continue anyway as this is not critical
            
            return True

        except dbus.exceptions.DBusException as e:
            Logger.error(f"DBus error restarting networking service: {e}")
            Logger.exception(e)
            return False
        except Exception as e:
            Logger.error(f"Error restarting networking service: {type(e).__name__}: {e}")
            Logger.exception(e)
            return False
        
    def change_network_settings_to_master(self):


        try:
            source = os.path.join(TEMPLATES_PATH, CONTROLLER_INTERFACES_TEMPLATE)
            target = '/etc/network/interfaces'
            shutil.copy2(source, target)
        except Exception as e:
            Logger.error(f"Error copying interfaces file: {e}")
