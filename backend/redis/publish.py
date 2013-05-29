#!/usr/bin/python
# --encoding:utf-8 --

import redis
import time

pool = redis.ConnectionPool(host="127.0.0.1", port=6379)
redis_client = redis.Redis(connection_pool=pool)

for i in xrange(1000):
    redis_client.publish("chat_room", "%s has sent..." % i)
    time.sleep(1)
    
