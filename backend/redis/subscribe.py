#!/usr/bin/python
# --encoding:utf-8 --

import redis
import time

pool = redis.ConnectionPool(host='127.0.0.1', port=6379)
redis_client = redis.Redis(connection_pool=pool)

pub = redis_client.pubsub()
pub.subscribe("chat_room")
listen = pub.listen()

while 1:
    print listen.next()
