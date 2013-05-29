#!/usr/bin/python
#! --encoding:utf-8 --
import os
import sys
import json
import time
import uuid

from redis_client import c, c_pipe
from common.logger import LOG


# 跨进程/服务器的部署中，服务器进程之间传递消息通过多播通信
# 包括但不限于下列消息:
# 同一个房间的消息
# 全局命令的同步
# 全局广播消息，例如大厅到各房间、用户上下线的全局通知等

# 房间和房间的消息队列信息保存在redis
# 下面为对应的数据结构说明
# hashtable: "room:1" 房间id为1的房间信息
# list: "chat:queue:1" 房间id为1的房间消息缓存列表
# string: room:counts 房间总数，整数类型
# list: "userlist:room:1" 房间id为1的用户列表
# hashtable: "user-123456" 用户的详细信息

def gen_uuid():
    return str(uuid.uuid4()).replace("-", "")

room_prefix = "room:"
chat_queue_prefix = "chat:queue:"
userlist_prefix = "userlist:"

# settings for default chat room
default_room_id = 1
default_room_magic_id = gen_uuid()
default_room_name = "默认聊天室"
default_room_max_user = 100
default_room_msg_cache_size = 100
default_room_key = room_prefix + str(default_room_id)


# settings for lobby room
lobby_room_id = 2
lobby_room_magic_id = gen_uuid()
lobby_room_name = "Lobby"
lobby_room_max_user = 10240000
lobby_room_msg_cache_size = 500
lobby_room_key = room_prefix + str(lobby_room_id)

room_count_key = room_prefix + "counts"
room_count = 0

global_room_max_user = 1000


# suspend callback(client) have to storage in local process
room_list = list()

default_room_waiter = dict(
    room_id = default_room_id,
    room_waiter_list = dict()
)

lobby_room_waiter = dict(
    room_id = lobby_room_id,
    room_waiter_list = dict()
)

room_list.append(default_room_waiter)
room_list.append(lobby_room_waiter)

def key_exists(key):
    """
    check the key is existes or not
    can use for string and hashtable
    """
    if c.exists(key):
        return True
    else:
        return False

def h_key_exists(name, key):
    if c.hexists(name, key):
        return True
    else:
        return False


# 如果redis做数据持久化存储
# 服务器进程启动时需要根据redis中保存的房间列表
# 重建每个本地的房间信息
# 是否使用持久化存储，应从一个全局配置文件中取得
def rebuild_room_waiter():
    max_room_id = get_max_room_id()
    if not max_room_id:
        return False
    for i in range(max_room_id - 1):
        room = dict(
            room_id = i + 1,
            room_waiter_list = set()
        )
        room_list.append(room)
    return True


def install_default_room():
    if not key_exists(default_room_key):
        c_pipe.hset(default_room_key, "room_id", default_room_id)
        c_pipe.hset(default_room_key, "room_magic_id", default_room_magic_id)
        c_pipe.hset(default_room_key, "room_name", default_room_name)
        c_pipe.hset(default_room_key, "room_max_user", default_room_max_user)
        c_pipe.hset(default_room_key, "room_cache_size", default_room_msg_cache_size)
        c_pipe.set(room_count_key, 1)
        c_pipe.execute()
        return True
    return False


def install_lobby_room():
    if not key_exists(lobby_room_key):
        c_pipe.hset(lobby_room_key, "room_id", lobby_room_id)
        c_pipe.hset(lobby_room_key, "room_magic_id", lobby_room_magic_id)
        c_pipe.hset(lobby_room_key, "room_name", lobby_room_name)
        c_pipe.hset(lobby_room_key, "room_max_user", lobby_room_max_user)
        c_pipe.hset(lobby_room_key, "room_cache_size", lobby_room_msg_cache_size)
        c_pipe.set(room_count_key, 2)
        c_pipe.execute()
        return True
    return False


if not install_default_room():
    LOG.info("This is just a WARNNING!\n" \
          "Install default room failed!\n" \
          "Maybe room was existed.\n")


if not install_lobby_room():
    LOG.info("This is just a WARNNING!\n" \
          "Install lobby room failed!\n" \
          "Maybe room was existed.\n")


class UserManager(object):
    def __init__(self):
        pass

    @staticmethod
    def user_add(room_id, user, handler):
        cls = UserManager
        userlist_set = userlist_prefix + room_prefix + str(room_id)
        c.sadd(userlist_set, user)
        cls.userinfo_add(room_id, user, handler)
    
    @staticmethod
    def user_del(room_id=None, user=None):
        # 如果用户访问/logout, 循环删除多个房间内的同一个用户
        # 否则只是用户关闭了浏览器标签, 删除对应房间的用户
        if not room_id:
            userlist_all = userlist_prefix + room_prefix + "[0-9]*"
            keys = c.keys(userlist_all)
            for key in keys:
                if c.sismember(key, user):
                    c.srem(key, user)
        else:
            cls = UserManager
            # 首先从删除某个房间内的用户
            userlist_set = userlist_prefix + room_prefix + str(room_id)
            c.srem(userlist_set, user)
            # 再判断此用户是否还在别的房间，如果不是则删除用户
            # 删除用户已改为设置用户离线标志
            cls.userinfo_del(user)
    
    @staticmethod
    def user_welcome(user):
        send = c.hget(user, "send_welcome")
        if send == "no" or send == None:
            c.hset(user, "send_welcome", "yes")
            return True
        elif send == "yes":
            return False
    
    @staticmethod
    def del_user_welcome(user):
        c.hdel(user, "send_welcome")
    
    @staticmethod
    def userinfo_add(room_id, user, handler):
        if not key_exists(user):
            c_pipe.hset(user, "current_room", room_id)
            c_pipe.hset(user, "remote_ip", handler.request.remote_ip)
            c_pipe.hset(user, "login_datetime", time.strftime("%Y-%m-%d %H:%M"))
        else:
            c_pipe.hset(user, "current_room", room_id)
            c_pipe.hset(user, "remote_ip", handler.request.remote_ip)
            
        c_pipe.hset(user, "offline", "no")
        c_pipe.execute()

    @staticmethod
    def userinfo_del(user):
        """
        因为这个用户信息是不和任何房间关联的
        所以要先判断用户，是否已经不在任何聊天室内
        如果是则删除用户
        """
        userlist_all = userlist_prefix + room_prefix + "[0-9]*"
        keys = c.keys(userlist_all)
        for key in keys:
            users = list(c.smembers(key))
            if user in users:
                return
        # 不删除用户的信息, 在userinfo_add中覆盖
        # 否则浏览器刷新会导致调用user_del
        # 改为设置用户离线标志
        # c.delete(user)
        c.hdel(user, "offline")
    
    @staticmethod
    def is_user_online(user):
        online = c.hget(user, "offline")
        if online == None:
            return False
        else:
            return True
    
    @staticmethod
    def set_user_offline(user):
        c.hdel("user", "offline")
    
    @staticmethod
    def is_local_user(user):
        """
        当一个用户进入多个房间的时候
        返回所有和这个用户相关的回调连接
        (言下之意，连接不止一个, 虽然只有一个用户)
        """
        user_waiters = list()
        for room in room_list:
            if user in room['room_waiter_list']:
                user_waiters.append(room['room_waiter_list'][user])
        if user_waiters:
            LOG.info("got %s conn for user: %s" % (len(user_waiters), user))
            return user_waiters
        return False
    
    @staticmethod
    def is_user_exists(user):
        '''
        判断用户是否存在
        如果用户已经存于redis中，而且用户当前在线则为真
        
        否则当用户没有存在与redis中时，则用户从未登录过
        或者用户当前不在线，使用相同的用户名登录会覆盖用户信息
        以上两种情况为假
        '''
        cls = UserManager
        if key_exists(user) and cls.is_user_online(user):
            return True
        else:
            return False
    
    @staticmethod
    def get_all_user_info():
        '''
        返回所有房间的用户，和用户的详细信息
        '''
        userlist_all = userlist_prefix + room_prefix + "[0-9]*"
        keys = c.keys(userlist_all)
        final_list = list()
        for key in keys:
            room_list = dict()
            room_list[key] = list()
            room_users = c.smembers(key)
            for user in room_users:
                user_detail = dict()
                user_detail[user] = c.hgetall(user)
                room_list[key].append(user_detail)
            final_list.append(room_list)
        return final_list
    
    @staticmethod
    def get_room_user(room_id):
        roomuser_key = userlist_prefix + room_prefix + str(room_id)
        room_users = c.smembers(roomuser_key)
        user_list = list()
        for user in room_users:
            temp = dict()
            temp['user'] = user
            temp['remote_ip'] = c.hget(user, "remote_ip")
            user_list.append(temp)
        return user_list

class WaiterManager(object):
    def __init__(self):
        pass
    
    @staticmethod
    def get_all_local_waiter():
        lists = list()
        for room in room_list:
            waiters = room['room_waiter_list'].values()
            for waiter in waiters:
                lists.append(waiter)
        return lists
    
    @staticmethod
    def add_waiter(callback, room_id, user):
        for room in room_list:
            if int(room_id) == room['room_id']:
                room['room_waiter_list'][user] = callback

    @staticmethod
    def empty_waiter(room_id):
        """
        clear all the suspended callback(client) for the room
        """
        for room in room_list:
            if int(room_id) == room['room_id']:
                room['room_waiter_list'] = dict()
    
    @staticmethod
    def remove_waiter(room_id, user):
        """
        delete a suspended callback(client) for a room
        """
        for room in room_list:
            if int(room_id) == room['room_id']:
                # 当一个用户多次进入同一个聊天室
                # 例如在同一个浏览器里打开多个窗口/标签
                # 忽略错误，是为了防止从room_waiter_list这个字典中多次pop同一个key
                try:
                    room['room_waiter_list'].pop(user)
                except Exception, e:
                    pass
    
    @staticmethod
    def remove_all_waiter(user):
        '''
        从本地的所有房间列表里移除用户
        '''
        for room in room_list:
            try:
                room['room_waiter_list'].pop(user)
            except Exception, e:
                pass
    
    @staticmethod
    def get_waiters_for_room_id(room_id):
        for room in room_list:
            if int(room_id) == room['room_id']:
                return room['room_waiter_list'].values()
        return list()


class ChatroomManager(object):
    def __init__(self):
        pass

    @staticmethod
    def get_max_room_id():
        max_room_id = int(c.get(room_count_key))
        if not max_room_id:
            return False
        return max_room_id


    @staticmethod
    def init_remote_chat_room(room_id):
        remote_room = dict(
            cmd = "add_chatroom",
            room_id = room_id
        )
        return remote_room


    @staticmethod
    def add_local_chat_room(room_id):
        room_custom = dict(
            room_id = room_id,
            room_waiter_list = dict()
        )
        room_list.append(room_custom)
        return True
    
    @staticmethod
    def check_room_id(room_id):
        room_key = room_prefix + str(room_id)
        if key_exists(room_key):
            return True
        else:
            return False

    @staticmethod
    def get_room_name(room_id):
        room_key = room_prefix + str(room_id)
        if key_exists(room_key):
            room_name = c.hget(room_key, "room_name")
            if room_name:
                return room_name
        return False
    
    @staticmethod
    def get_users_for_room_id(room_id):
        userlist_set = userlist_prefix + room_prefix + str(room_id)
        return c.smembers(userlist_set)

    @staticmethod
    def get_room_list():
        lists = list()
        all_room_keys = c.keys(room_prefix + "[0-9]*")
        for room_key in all_room_keys:
            temp = dict()
            room_id = int(c.hget(room_key, "room_id"))
            if room_id != lobby_room_id:
                temp['room_id'] = room_id
                temp['room_magic_id'] = c.hget(room_key, "room_magic_id")
                temp['room_name'] = c.hget(room_key, "room_name")
                temp['room_max_user'] = c.hget(room_key, "room_max_user"),
                temp['room_waiter_list'] = len(ChatroomManager.get_users_for_room_id(room_id))
                lists.append(temp)
    
        lists.sort()
        return lists
    
    @staticmethod
    def magic_2_normal(magic_id):
        room_keys = c.keys(room_prefix + "[0-9]*")
        for room in room_keys:
            if c.hget(room, "room_magic_id") == magic_id:
                return int(c.hget(room, "room_id"))

    @staticmethod
    def add_chat_room(room_name, room_max_user, room_cache_size=50):
        max_room_id = ChatroomManager.get_max_room_id()
        if not max_room_id:
            return False
        
        room_key = room_prefix + str(max_room_id + 1)
        if key_exists(room_key):
            return False
        
        try:
            room_max_user = int(room_max_user)
        except Exception, e:
            LOG.info("the parameter 'room_max_user' is not a digest!")
            room_max_user = default_room_max_user
        else:
            if room_max_user > global_room_max_user:
                LOG.info("maximum user in chat room must less than 1000.")
                return False
        
        room_id = ChatroomManager.get_max_room_id() + 1
        c_pipe.hset(room_key, "room_id", room_id)
        c_pipe.hset(room_key, "room_magic_id", gen_uuid())
        c_pipe.hset(room_key, "room_name", room_name)
        c_pipe.hset(room_key, "room_max_user", room_max_user)
        c_pipe.hset(room_key, "room_cache_size", room_cache_size)
        c_pipe.execute()
        
        room_custom = dict(
            room_id = room_id,
            room_waiter_list = dict()
        )
        room_list.append(room_custom)
        
        c.getset(room_count_key, room_id)
        return room_id
    

class MessageCacheManager(object):
    def __init__(self):
        pass

    @staticmethod
    def get_room_cache_size(room_id):
        room_key = room_prefix + str(room_id)
        if key_exists(room_key):
            room_cache_size = c.hget(room_key, "room_cache_size")
            if room_cache_size:
                return int(room_cache_size)
        return False
    
    @staticmethod
    def add_msg_cache(messages, room_id):
        chat_queue_name =  chat_queue_prefix + str(room_id)
        if c.llen(chat_queue_name) >= MessageCacheManager.get_room_cache_size(room_id):
            c.lpop(chat_queue_name)
        c.rpush(chat_queue_name, messages)
        return True

    @staticmethod
    def get_msg_for_room_id(room_id):
        chat_queue_name = chat_queue_prefix + str(room_id)
        queue_len = c.llen(chat_queue_name)
        if not queue_len:
            return list()
        
        msg_list = c.lrange(chat_queue_name, 0, -1)
        
        lists = list()
        for msg in msg_list:
            lists.append(eval(msg)[0])
        return lists


class SignalHandlerManager(object):
    def __init__(self):
        pass
    
    @staticmethod
    def on_server_exit():
        room_userlist_all = userlist_prefix + room_prefix + "[0-9]*"
        keys = c.keys(room_userlist_all)
        for key in keys:
            users = c.smembers(key)
            for user in users:
                c.delete(user)
                
            c.delete(key)

