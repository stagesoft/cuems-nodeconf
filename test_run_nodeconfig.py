
from zeroconf import IPVersion, ServiceInfo, ServiceListener, ServiceBrowser, Zeroconf, ZeroconfServiceTypes
import socket
import netifaces
import time
import uuid

import logging
import sys

import threading

from CuemsAvahiListener import CuemsAvahiListener
from CuemsConfServer import CuemsConfServer
logging.basicConfig(level=logging.DEBUG,
                    format='%(name)s: %(message)s',
                    )



iface = netifaces.gateways()['default'][netifaces.AF_INET][1]
ip = netifaces.ifaddresses(iface)[netifaces.AF_INET][0]['addr']
str_uuid = str(uuid.uuid4())
hostname = socket.gethostname()
server = f"{hostname}.local."

# for serviceinfo

type_ = "_cuems-nodeconf._tcp.local."
name = f"{str_uuid} Cuems on {hostname}._cuems-nodeconf._tcp.local."
port = 9000

service_info = ServiceInfo(
        type_,
        name,
        addresses=[socket.inet_aton(ip)],
        port=port,
    )


zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
# services = ["_cuems_node._tcp.local.", "_cuems-nodeconf._tcp.local."]
services = [type_]
#services = ["_cuems-nodeconf._tcp.local."]
listener = CuemsAvahiListener()

browser = ServiceBrowser(zeroconf, services, listener)

def find_master(nodes):
    if nodes.master:
        return True
        
    return False

def register_node(zeroconf_instance, server, service_info, master_exists):
    
    if not master_exists:
        node_role = 'controller'
        logger.debug("no master in network, We are master!")
    else:
        node_role = 'node'
        logger.debug("master present, We stay as slave")

    service_info = ServiceInfo(
        type_,
        name,
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={'node_role' : node_role },
        server=server,
        host_ttl=10,
        other_ttl=10,
    )

    zeroconf_instance.register_service(service_info)    


try:
    logger = logging.getLogger('main')
    time.sleep(2)
    logger.debug("Registering service")
    master_exists = find_master(listener.nodes)
    register_node(zeroconf, server, service_info, master_exists)
    if not master_exists:
        logger.info('Master: starting server on %s:%s', ip, port)
        address = (server, port)  # let the kernel assign a port
        echo_server = CuemsConfServer(address)
        ip, port = echo_server.server_address  # what port was assigned?
        t = threading.Thread(target=echo_server.serve_forever)
        t.setDaemon(True)  # don't hang on exit
        t.start()
        
        logger.info('Server on %s:%s', ip, port)
    else:
        logger = logging.getLogger('client')
        logger.info('conecting to master on %s:%s', listener.nodes.master[0].ip, port)
        # Connect to the server
        logger.debug('creating socket')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logger.debug('connecting to server')
        s.connect((listener.nodes.master[0].ip, port))

        # Send the data
        message = f'Hello from {server}, slave node with uuid: {str_uuid}'.encode()
        logger.debug(f'sending data: {message}')
        len_sent = s.send(message)

        # Receive a response
        logger.debug('waiting for response')
        response = s.recv(len_sent)
        logger.debug(f'response from server: {response}')

    logger = logging.getLogger('main')
    if listener.nodes.master:
        logger.debug(f"master: {listener.nodes.master}")
    else:
        raise Exception("we have no master!!")
    if listener.nodes.slaves:
        logger.debug(f"we have {len(listener.nodes.slaves)} slaves")
        logger.debug(f"slaves: {listener.nodes.slaves}")
    else:
        logger.debug("we have no slaves")

#    print('\n'.join(ZeroconfServiceTypes.find(zc=zeroconf)))

    

    

    input("Press enter to exit...\n\n")
    
finally:
    logger.debug("Unregistering...")
    zeroconf.unregister_service(service_info)
    zeroconf.close()
    logger.debug('closing socket')
    try:
        s.close()
    except NameError:
        pass
        
    try:
        echo_server.shutdown()
        echo_server.socket.close()
    except NameError:
        pass


