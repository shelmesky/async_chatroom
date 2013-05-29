import socket
import struct
from tornado import ioloop
from tornado.options import options
import functools
 
multicast_addr = options.multicast_addr
bind_addr = options.multicast_bind_addr
port = options.multicast_port
 

def make_sock():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind_addr, port))
    
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    
    intf = socket.gethostbyname(socket.gethostname())
    sock.setsockopt(socket.SOL_IP, socket.IP_MULTICAST_IF,
                    socket.inet_aton(intf) + socket.inet_aton('0.0.0.0'))
    
    membership = socket.inet_aton(multicast_addr) + socket.inet_aton(bind_addr)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
    
    return sock

 
def add_callback(callback):
    def conn_callback(sock, fd, events):
        callback(sock)
    sock = make_sock()
    io_loop = ioloop.IOLoop.instance()
    handler = functools.partial(conn_callback, sock)
    io_loop.add_handler(sock.fileno(), handler, io_loop.READ)
    return io_loop


def test_multicast(conn):
    data, address = conn.recvfrom(1024)
    print data, address

if __name__ == '__main__':
    io_loop = add_callback(test_multicast)
    io_loop.start()

