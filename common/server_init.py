from tornado.options import define, options
import tornado.options

conf_file = "server.conf"

def server_init():
    define("port", help="run on the given port", type=int)
    
    define("redis_host", help="the server of redis", type=str)
    define("redis_port", help="the port of redis server", type=int)
    define("redis_db", help="which db will be used in redis", type=int)
    
    define("multicast_addr", help="multicast group", type=str)
    define("multicast_port", help="port of multicast group", type=int)
    define("multicast_bind_addr", help="multicast bind addr", type=str)
    
    define("template_dir", help="dir which template storage", type=str)
    define("static_dir", help="dir which static file storage", type=str)
    define("cookie_secret", help="secret of cookie of init use", type=str)
    
    define("encrypt_key", help="key use to encrypt content that transfer by multicast", type=str)
    tornado.options.parse_config_file(conf_file)