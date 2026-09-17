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

# feature 007: the node model lives in cuemsutils now — see
# specs/007-node-model-migration/migration-guide.md in cuems-utils for the
# full moved-symbol table. `node` is aliased because this module (like the
# rest of the package) uses `node` pervasively as a loop/local variable name.
from cuemsutils.tools.NodeList import NodeIndex, NodeRole
from cuemsutils.tools.NodeList import node as Node
from cuemsutils.config.network_map import CuemsNetworkMapType
from cuemsutils.tools.ConfigManager import ConfigManager
from cuemsutils.errors import SchemaError

from cuemsutils.tools.TimeoutLoop import TimeoutLoop
from cuemsutils.log import Logger, logged
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
        self.network_map = NodeIndex()

        self.services = ['_cuems_nodeconf._tcp.local.']

        # Daemon lifecycle / long-running state.
        self.running = False
        self.stop_requested = False
        # Set by avahi discovery callbacks; the worker loop wakes on it.
        self._dirty = threading.Event()
        # Owe the next refresh a write even if nothing changed: at start-up (the
        # first discovery pass always writes the map) and after any write that
        # failed (a failure is retried every pass, not only on the next change).
        # CuemsNetworkMapType.refresh decides whether *discovery* changed the
        # map; it cannot know that the disk is behind.
        self._map_write_pending = True
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

        self.is_first_run = not os.path.isfile(self.map_path)
        if not self.is_first_run:
            Logger.debug('Reading existing network_map.xml')
            self.read_network_map()
        else:
            Logger.debug('No existing network_map.xml found, starting fresh')
            self.network_map = NodeIndex()

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
        if self.node['node_role'] == NodeRole.firstrun:
            if self._should_resume_master():
                # This host was the controller before (master.lock present, or
                # the existing network_map already records this node as master).
                # Resume that role instead of re-running the firstrun election.
                # We only reinstate the avahi service template here; the network
                # is assumed already in master configuration (do NOT restart
                # networking on a resume — that is disruptive and unnecessary).
                Logger.info('Resuming master role from existing state (skipping firstrun election)')
                self.node['node_role'] = NodeRole.controller
                self._install_master_service_template()
            else:
                Logger.debug("First time conf file detected, triying to autoconfigure node")
                self.set_node_role()
        else:
            Logger.debug(f"Allready configured as {self.node['node_role'].name}")

        # If I am master, give slaves a moment to appear before the first pass.
        if self.node['node_role'] == NodeRole.controller:
            time.sleep(5)
        self.publish_aliases_if_master()

        if self.listener.nodes.by_role(NodeRole.firstrun):
            Logger.debug('Waiting for some other "first-run" nodes')
        # Add timeout to prevent infinite loop
        max_iterations = 60  # 30 seconds max (60 * 0.5)
        iteration = 0
        while self.listener.nodes.by_role(NodeRole.firstrun) and iteration < max_iterations:
            time.sleep(0.5)
            iteration += 1
        if iteration >= max_iterations and self.listener.nodes.by_role(NodeRole.firstrun):
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

        The merge, the controller-always-adopted rule and the write-if-changed
        decision are CuemsNetworkMapType.refresh's (feature 001, D22). The index
        in self.network_map stays the single in-memory source of truth: a
        document is built from it for each pass and read back into it after, so
        an operator adoption made between passes is never lost to a stale copy.
        """
        discovered = self.listener.nodes
        document = self._network_map_document()
        try:
            wrote = document.refresh(discovered, self.map_path)
            if not wrote and self._map_write_pending:
                document.save(self.map_path)
                wrote = True
            self._map_write_pending = False
            if not wrote:
                Logger.debug('network_map unchanged; skipping write')
        except PermissionError as e:
            self._map_write_pending = True
            Logger.error(f"Permission denied writing network map to {self.map_path}: {e}")
            Logger.exception(e)
        except Exception as e:
            self._map_write_pending = True
            Logger.error(f"Error writing network map: {type(e).__name__}: {e}")
            Logger.exception(e)
        finally:
            # refresh reassigns node_list before it saves, so this is the merged
            # state whether or not the write landed.
            self.network_map = self._index_from_document(document)

        # Reporting only — deliberately outside refresh's orchestration (FR-007).
        missing = self.network_map.missing_adopted(discovered)
        if missing:
            labels = [f"{n.get('name')} ({n.get('uuid')})" for n in missing]
            Logger.warning(f'Missing adopted nodes: {labels}')
        else:
            Logger.debug('All adopted nodes are present')

    def _network_map_document(self):
        """The persisted form of self.network_map, built fresh from the index."""
        return CuemsNetworkMapType(node_list=[{"node": n} for n in self.network_map.values()])

    @staticmethod
    def _index_from_document(document):
        """The MAC-keyed index over a network-map document's nodes (no copies)."""
        index = NodeIndex()
        for item in document.get('node_list') or []:
            node = item.get('node') if isinstance(item, dict) else item
            index[node['mac']] = node
        return index

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

    def notify_systemd(self, status='READY=1'):

        Logger.debug('Startup complete, notifying systemd')
        systemd.daemon.notify(status)
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
        for passed in TimeoutLoop(timeout=10, interval=1):
            try:
                self.ip = netifaces.ifaddresses('bridge0:avahi')[netifaces.AF_INET][0]['addr']
                self.cluster_iface = 'bridge0'
                Logger.debug(f"Found bridge0:avahi interface, IP: {self.ip}")
                return
            except (ValueError, KeyError):
                Logger.debug("bridge0:avahi interface not found, triying next ones")
                try:
                    self.ip = netifaces.ifaddresses('ethernet1:avahi')[netifaces.AF_INET][0]['addr']
                    self.cluster_iface = 'ethernet1'
                    Logger.debug(f"Found ethernet1:avahi interface, IP: {self.ip}")
                except (ValueError, KeyError):
                    Logger.debug("Waiting for ethernet1:avahi interface to appear")

                try:
                    self.controller_ip = netifaces.ifaddresses('bond0')[netifaces.AF_INET][0]['addr']
                    self.ui_iface = 'bond0'
                    if self.ip != None:
                        Logger.debug(f"Found bond0 interface, CONTROLLER IP: {self.controller_ip}")
                        return
                    else:
                        Logger.debug(f"Found bond0 interface, but we are mising ethernet1:avahi interface, continuing")
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
            own = self.network_map.get(self.node['mac'])
            if own is not None and own.get('node_role') == NodeRole.controller:
                Logger.debug('existing network_map records this node as master -> resume master')
                return True
        except Exception:
            pass
        return False

    def _install_master_service_template(self):
        """Copy the master avahi service template into place (idempotent)."""
        source = os.path.join(TEMPLATES_PATH, CUEMS_SERVICE_FILE) + '.controller'
        target = os.path.join('/etc/avahi/services/', CUEMS_SERVICE_FILE)
        try:
            shutil.copy2(source, target)
        except FileNotFoundError:
            Logger.error(f"Controller service template not found at {source}")
            raise
        except PermissionError:
            Logger.error(f"Permission denied copying service template to {target}")
            raise
        except Exception as e:
            Logger.error(f"Error copying master service template: {type(e).__name__}: {e}")
            Logger.exception(e)
            raise

    def set_node_role(self):
        if not self.listener.nodes.controllers:
            Logger.debug('No master node on the network, I become MASTER!')
            self.node['node_role'] = NodeRole.controller

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
            self.node['node_role'] = NodeRole.node

            # Copy slave node service template. nodeconf runs as root, so a
            # direct copy is correct here — the old `sudo cp` shelled out
            # needlessly and silently fails when sudo isn't passwordless.
            source = os.path.join(TEMPLATES_PATH, CUEMS_SERVICE_FILE) + '.node'
            target = os.path.join('/etc/avahi/services/', CUEMS_SERVICE_FILE)
            try:
                shutil.copy2(source, target)
            except FileNotFoundError:
                Logger.error(f"Node service template not found at {source}")
                raise
            except Exception as e:
                Logger.error(f"Error copying slave service template: {type(e).__name__}: {e}")
                Logger.exception(e)
                raise
        
    def _save_network_map(self):
        """Write self.network_map now; a write that fails is owed to the next refresh.

        CuemsNetworkMapType.save validates against network_map.xsd before
        writing atomically, so the old pre-save required-field check is gone:
        the schema already rejects the same documents (FR-008).
        """
        try:
            self._network_map_document().save(self.map_path)
        except SchemaError as e:
            self._map_write_pending = True
            Logger.error(f"Network map failed validation: {e}")
            raise
        except Exception:
            self._map_write_pending = True
            raise
        self._map_write_pending = False
        Logger.debug("Network map written to XML (atomic)")

    def _find_node(self, node_uuid):
        return next((n for n in self.network_map.values() if n.get('uuid') == node_uuid), None)

    def adopt_node(self, node_uuid):
        """Adopt through NodeIndex.adopt, shaping the RPC answer engine_callback sends.

        NodeIndex.adopt returns a bare bool and does not persist (feature 001,
        FR-003/FR-010). So: a False is two-way ambiguous — absent or offline —
        and is told apart by looking the uuid up; "already adopted" is detected
        by the signature not moving, not by re-coding the adoption rule; and a
        real change is saved BEFORE the answer, as it always was.
        """
        before = self.network_map.signature()
        if not self.network_map.adopt(node_uuid):
            if self._find_node(node_uuid) is None:
                Logger.warning(f'Node {node_uuid} not found in network_map')
                return {'OK': False, 'error': f'Node {node_uuid} not found'}
            Logger.warning(f'Cannot adopt node {node_uuid}: node is offline')
            return {'OK': False, 'error': f'Cannot adopt node {node_uuid}: node is offline'}
        if self.network_map.signature() == before:
            Logger.debug(f'Node {node_uuid} is already adopted')
            return {'OK': True, 'message': 'Node already adopted'}
        self._save_network_map()
        Logger.info(f'Node {node_uuid} adopted')
        return {'OK': True}

    def unadopt_node(self, node_uuid):
        """Unadopt through NodeIndex.unadopt; see adopt_node for the shape.

        Here the ambiguous False means absent or the controller. Offline nodes
        can and should be unadoptable, so stale entries can be cleaned up.
        """
        before = self.network_map.signature()
        if not self.network_map.unadopt(node_uuid):
            if self._find_node(node_uuid) is None:
                Logger.warning(f'Node {node_uuid} not found in network_map')
                return {'OK': False, 'error': f'Node {node_uuid} not found'}
            Logger.warning(f'Cannot unadopt master node {node_uuid}')
            return {'OK': False, 'error': 'Cannot unadopt master node'}
        if self.network_map.signature() == before:
            Logger.debug(f'Node {node_uuid} is already unadopted')
            return {'OK': True, 'message': 'Node already unadopted'}
        if not self._find_node(node_uuid).get('online'):
            Logger.info(f'Unadopting offline node {node_uuid} (node is not online)')
        self._save_network_map()
        Logger.info(f'Node {node_uuid} unadopted')
        return {'OK': True}

    def read_network_map(self):
        # feature 007 (T075): both legacy spellings of the retired element are gone after
        # the postinst conversion (cuems-common M3) — network_map's own
        # adapter table now decodes node_role straight to NodeRole (R1), so
        # there is nothing left to normalise here.
        # Through the public config object (FR-013). ConfigManager needs
        # settings.xml beside the map; every node has both, provisioned by
        # nodeconf's cuems-utils and cuems-common dependencies.
        manager = ConfigManager(config_dir=os.path.dirname(self.map_path), load_all=False)
        try:
            manager.load_network_map()
        except ValueError:
            # load_network_map ends by resolving THIS node's own entry, and
            # raises when the map does not list it yet -- which is every freshly
            # provisioned node: cuems-config-node gives settings.xml a new uuid
            # and leaves the map alone. nodeconf is what writes this node into
            # the map (the engine cannot start until it has), so it must read
            # such a map. By then the map is loaded and validated; a broken
            # document raises SchemaError, which is not a ValueError. If the map
            # was not populated, this was something else: let it propagate.
            if not hasattr(manager, 'network_map'):
                raise
            Logger.info('This node is not in network_map.xml yet; discovery will add it')
        self.network_map = self._index_from_document(manager.network_map)

        Logger.debug("---")
        Logger.debug("Nodes read from existing XML network map:")
        for item, value in self.network_map.items():
            Logger.debug(f"{value}")
        Logger.debug("---")

    def callback(self, caller_node=None, action=CuemsAvahiListener.Action.ADD):
        Logger.debug(f" {action} callback!!!, Node: {caller_node} ")

        self.check_nodes()

    def check_nodes(self):
        # Logger.debug(self.listener.nodes)
        controllers = self.listener.nodes.controllers
        if controllers:
            Logger.debug(f"Controller node(s):\n{controllers}")
        else:
            Logger.debug(f"We have no controller!! yet? waiting for it")
        plain_nodes = self.listener.nodes.by_role(NodeRole.node)
        if plain_nodes:
            Logger.debug(
                f"We have {len(plain_nodes)} nodes")
            Logger.debug(f"Node(s):\n{plain_nodes}")
        else:
            Logger.debug("we have no nodes")

    def check_first_run(self):
        for node in self.listener.nodes.by_role(NodeRole.firstrun):
            if node.get('ip') == self.ip:
                return True

        return False
    
    def wait_for_local_service_registration(self):
        """
        Wait for the local service to be registered and discovered by the Avahi listener.
        This ensures the service is available before we try to retrieve it.
        """
        for passed in TimeoutLoop(timeout=5, interval=0.2):
            for node in self.listener.nodes.values():
                if node.get('ip') == self.ip:
                    Logger.debug(f"Local service registered and discovered: {node.get('name')}")
                    return
            
            Logger.debug("Waiting for local service to be registered...")
        
        # Timeout occurred - TimeoutLoop will raise TimeoutError
        raise TimeoutError('Local service registration not detected within timeout period')

    def retreive_local_node(self):
        for passed in TimeoutLoop(timeout=10, interval=1):
            for node in self.listener.nodes.values():
                if node.get('ip') == self.ip:
                    return node

            Logger.debug("waiting for local node to appear on the network")
        
        # Timeout occurred - TimeoutLoop will raise TimeoutError
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
        if node is None or node.get('node_role') != NodeRole.controller:
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
        if self.node.get('node_role') == NodeRole.controller:
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
