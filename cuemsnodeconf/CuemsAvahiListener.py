from .CuemsNode import CuemsNodeDict, CuemsNode
import enum

from cuemsutils.log import main_logger

# NOTE: this module used to call logging.basicConfig() at import time and hang
# its 'Avahi-listener' logger off the root handler that call installed. Since
# cuemsutils.log seeds the root logger with a NullHandler (to stop third-party
# import-time logging from re-emitting every record in BASIC_FORMAT), that
# basicConfig became a no-op and the listener's output went nowhere. The logger
# now comes from cuemsutils.main_logger like every other module in this
# package, which handles systemd vs terminal output and real syslog priorities.


class CuemsAvahiListener():
    @enum.unique
    class Action(enum.Enum):
        DELETE = 0
        ADD = 1
        UPDATE = 2

    def __init__(self, ip, callback = None):
        self.ip = ip
        self.callback = callback
        # Per-instance node table. (Was a class attribute, which shared state
        # across every listener instance and leaked between tests; a
        # long-running daemon must not share discovery state across restarts.)
        self.nodes = CuemsNodeDict()
        self.logger = main_logger('Avahi-listener')

    def get_mac(self, name):
        return name[:12]

    def remove_service(self, zeroconf, type_, name):
        self.logger.debug(f'Service {name} removed')

        # Drop the departed node from the table so the next merge pass marks it
        # offline. Without this, merge_discovered_nodes() never sees the
        # departure and <online> stays True forever for vanished nodes.
        mac = self.get_mac(name)
        removed = self.nodes.pop(mac, None)

        if self.callback:
            self.callback(removed, action=CuemsAvahiListener.Action.DELETE)

    def add_service(self, zeroconf, type_, name):
        ip = None
        try:
            info = zeroconf.get_service_info(type_, name)
            if info is None:
                self.logger.error(f'Service info is None for {name}')
                return
            
            self.logger.debug(info)
            
            addresses = info.parsed_addresses()
            if not addresses:
                self.logger.error(f'No addresses found for service {name}')
                return
            
            if len(addresses) > 1:
                self.logger.debug(f'Multiple addresses found for {name}!')
                ## if ip is one of the internal interfaces, use that one, if not use the first one
                for address in addresses:
                    if address == self.ip:
                        ip = address
                        break
                if not ip:
                    ip = addresses[0]
            else:
                ip = addresses[0]

            self.logger.debug(f'node ip: {ip}')
            
            # Validate required properties exist
            if b'uuid' not in info.properties:
                self.logger.error(f'Missing uuid property for service {name}')
                return
            if b'node_type' not in info.properties:
                self.logger.error(f'Missing node_type property for service {name}')
                return
            
            node = CuemsNode({ 'uuid' : info.properties[b"uuid"].decode("utf-8"), 'mac' : self.get_mac(name), 'name' : name, 'node_type': CuemsNode.NodeType[info.properties[b'node_type'].decode("utf-8")] , 'ip' : ip, 'adopted': False, 'online': True})
            try:
                self.nodes[self.get_mac(name)].update(node)
            except KeyError:
                self.nodes[self.get_mac(name)] = node
            
            self.logger.debug(f'Service {name} added, service info: {info}')

            if self.callback:
                self.callback(node)
        except Exception as e:
            self.logger.error(f'Error in add_service for {name}: {e}')
            self.logger.exception(e)

    def update_service(self, zeroconf, type_, name):
        ip = None
        try:
            info = zeroconf.get_service_info(type_, name)
            if info is None:
                self.logger.error(f'Service info is None for {name}')
                return
            
            addresses = info.parsed_addresses()
            if not addresses:
                self.logger.error(f'No addresses found for service {name}')
                return
            
            if len(addresses) > 1:
                self.logger.debug(f'Multiple addresses found for {name}!')
                for address in addresses:
                    if address == self.ip:
                        ip = address
                        break
                if not ip:
                    ip = addresses[0]
            else:
                ip = addresses[0]
            
            # Validate required properties exist
            if b'uuid' not in info.properties:
                self.logger.error(f'Missing uuid property for service {name}')
                return
            if b'node_type' not in info.properties:
                self.logger.error(f'Missing node_type property for service {name}')
                return
            
            node = CuemsNode({ 'uuid' : info.properties[b"uuid"].decode("utf-8"), 'mac' : self.get_mac(name), 'name' : name, 'node_type': CuemsNode.NodeType[info.properties[b'node_type'].decode("utf-8")], 'ip' : ip, 'adopted': False, 'online': True})
            self.nodes[self.get_mac(name)].update(node)
            self.logger.debug(f'Service {name} updated, service info: {info}')

            if self.callback:
                self.callback(node, action=CuemsAvahiListener.Action.UPDATE)
        except Exception as e:
            self.logger.error(f'Error in update_service for {name}: {e}')
            self.logger.exception(e)