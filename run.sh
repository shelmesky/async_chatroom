#!/bin/sh
redis-server 1>./nohup.redis.log 2>&1 &
python ./server.py --port=10000 1>./nohup.0.log 2>&1 &
