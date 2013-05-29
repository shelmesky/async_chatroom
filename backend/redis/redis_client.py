#!/usr/bin/python
# --encoding:utf-8 --

import redis
from tornado.options import options

redis_host = options.redis_host
redis_port = options.redis_port
redis_db = options.redis_db


try:
    pool = redis.ConnectionPool(host=redis_host, port=redis_port, db=redis_db)
except Exception, e:
    raise


def connect_redis():
    redis_client = redis.Redis(connection_pool=pool)
    return redis_client


def connect_redis_pipeline():
    redis_client = redis.Redis(connection_pool=pool)
    pipe = redis_client.pipeline(transaction=False)
    return pipe


try:
    c = connect_redis()
    c_pipe = connect_redis_pipeline()
except Exception, e:
    raise


def make_simple_test():
    # make simple test
    try:
        from prettyprint.prettyprint import pp
        pp(c.config_get())
    except ImportError:
        print c.config_get()


if __name__ == '__main__':
    make_simple_test()
