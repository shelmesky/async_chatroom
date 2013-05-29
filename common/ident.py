#!/usr/bin/python
# --encoding:utf-8--

import os

def get_node_id(node_id):
    pid = os.getpid()
    return node_id + ":" + str(pid)