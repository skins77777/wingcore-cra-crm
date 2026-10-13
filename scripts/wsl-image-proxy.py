"""Forward only this project's WSL client to the existing Windows HTTP proxy."""
import argparse
import selectors
import socket
import socketserver

parser = argparse.ArgumentParser()
parser.add_argument('--listen', required=True)
parser.add_argument('--client', required=True)
parser.add_argument('--port', type=int, default=18080)
args = parser.parse_args()


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        if self.client_address[0] != args.client:
            return
        try:
            with socket.create_connection(('127.0.0.1', 10808), timeout=15) as upstream:
                upstream.settimeout(None)
                with selectors.DefaultSelector() as selector:
                    selector.register(self.request, selectors.EVENT_READ, upstream)
                    selector.register(upstream, selectors.EVENT_READ, self.request)
                    while True:
                        events = selector.select(timeout=120)
                        if not events:
                            return
                        for key, _ in events:
                            data = key.fileobj.recv(65536)
                            if not data:
                                return
                            key.data.sendall(data)
        except (OSError, TimeoutError):
            return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server((args.listen, args.port), Handler) as server:
    server.serve_forever()
