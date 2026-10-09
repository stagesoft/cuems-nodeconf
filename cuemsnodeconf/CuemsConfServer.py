
import socketserver
import json

from cuemsutils.log import main_logger

from .CuemsSettings import read_conf

class CuemsConfServerHandler(socketserver.BaseRequestHandler):
    settings_dict = read_conf()
    def __init__(self, request, client_address, server):
        self.logger = main_logger('CuemsConfServerHandler')
        self.logger.debug('__init__')
        socketserver.BaseRequestHandler.__init__(self, request,
                                                 client_address,
                                                 server)
        return

    def setup(self):
        self.logger.debug('setup')
        return socketserver.BaseRequestHandler.setup(self)

    def handle(self):
        self.logger.debug('handle')

        # Echo the back to the client
        data = self.request.recv(1024)
        data = data.decode("utf-8")
        self.logger.debug('recv()->"%s"', data)
        if 'Hello' in data:
            message = f"ACK {self.server.server_address}, slave node with uuid: {self.settings_dict['uuid']}".encode()
        elif "Conf" in data:
            message = json.dumps({'bla': 'ble', 'mas_conf': {'cositas': ['as', 'dos', 3]}}).encode()

        self.request.send(message)
        return

    def finish(self):
        self.logger.debug('finish')
        return socketserver.BaseRequestHandler.finish(self)

class CuemsConfServer(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, server_address,
                 handler_class=CuemsConfServerHandler,
                 ):
        self.logger = main_logger('CuemsConfServer')
        self.logger.debug('__init__')
        socketserver.TCPServer.__init__(self, server_address,
                                        handler_class)
        return

    def server_activate(self):
        self.logger.debug('server_activate')
        socketserver.TCPServer.server_activate(self)
        return

    def serve_forever(self, poll_interval=0.5):
        self.logger.debug('waiting for request')
        self.logger.info(
            'Handling requests, press <Ctrl-C> to quit'
        )
        socketserver.TCPServer.serve_forever(self, poll_interval)
        return

    def handle_request(self):
        self.logger.debug('handle_request')
        return socketserver.TCPServer.handle_request(self)

    def verify_request(self, request, client_address):
        self.logger.debug('verify_request(%s, %s)',
                          request, client_address)
        return socketserver.TCPServer.verify_request(
            self, request, client_address,
        )

    def process_request(self, request, client_address):
        self.logger.debug('process_request(%s, %s)',
                          request, client_address)
        return socketserver.TCPServer.process_request(
            self, request, client_address,
        )

    def server_close(self):
        self.logger.debug('server_close')
        return socketserver.TCPServer.server_close(self)

    def finish_request(self, request, client_address):
        self.logger.debug('finish_request(%s, %s)',
                          request, client_address)
        return socketserver.TCPServer.finish_request(
            self, request, client_address,
        )

    def close_request(self, request_address):
        self.logger.debug('close_request(%s)', request_address)
        return socketserver.TCPServer.close_request(
            self, request_address,
        )

    def shutdown(self):
        self.logger.debug('shutdown()')
        return socketserver.TCPServer.shutdown(self)

