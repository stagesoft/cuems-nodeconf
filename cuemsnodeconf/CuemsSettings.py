import socket
import netifaces
import uuid


def get_ip():
    return netifaces.ifaddresses('ethernet0:avahi')[netifaces.AF_INET][0]['addr']

def read_conf():
    # TEMP FIXX
    iface = netifaces.gateways()['default'][netifaces.AF_INET][1]
    mac = netifaces.ifaddresses(iface)[netifaces.AF_LINK][0]['addr']
    mac = f"MAC_instead_of_UUID{mac}"

    settings_dict = dict()
    settings_dict['ip'] = get_ip()
    settings_dict['uuid'] = mac
    settings_dict['hostname'] = socket.gethostname()
    settings_dict['server'] = f"{settings_dict['hostname']}.local."
    settings_dict['type_'] = "_cuems_nodeconf._tcp.local."
    settings_dict['name'] = f"{settings_dict['uuid']} Cuems node on {settings_dict['hostname']}._cuems-nodeconf._tcp.local."
    settings_dict['port'] = 9000
    # The Avahi TXT record key/value here is wire format. 'node' is this
    # node's default self-announcement before its role is determined (see
    # CuemsNodeConf.set_node_role) — the same meaning 'slave' carried before
    # feature 001's cutover, in the vocabulary NodeRole already uses.
    settings_dict['properties'] = {'node_role' : 'node'}
    settings_dict['host_ttl'] = 50
    settings_dict['other_ttl'] = 50

    return settings_dict
