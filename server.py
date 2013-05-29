#!/usr/bin/python
# --encoding: utf-8--

import os
import sys
import simplejson as json
import random
import uuid
import logging
import time
import functools
import uuid
import signal
import argparse
import socket

from common.server_init import server_init

server_init()

from tornado.options import define, options
import tornado.options

from tornado.web import RequestHandler
from tornado.web import Application
from tornado.httpserver import HTTPServer
from tornado.web import asynchronous
from tornado import ioloop
import tornado.options
from tornado.options import define, options

from common.logger import LOG

from backend.redis import redis_backend as redis
from backend.multicast.receiver import add_callback
from backend.multicast.sender import sender
from common.ident import get_node_id
from common import manager
from multicast_processor import multicast_processor
from multicast_processor import multicast_sender
from common.utlis import from_now_to_datetime

CommandManager = manager.CommandManager

node_name = str(uuid.uuid4())
local_node_id = get_node_id(node_name)

multicast_sender = functools.partial(multicast_sender,
                                     local_node_id=local_node_id)

multicast_processor = functools.partial(multicast_processor,
                                        local_node_id=local_node_id)


def multicast_receiver(conn):
    """
    Receive message from multicast channel.
    """
    multicast_processor(conn)
    

class iApplication(Application):
    """
    Settings and URL router.
    """
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/login", LoginHandler),
            (r"/room", RoomList),
            (r"/chat/([0-9a-z]+)", ChatMain),
            (r"/message/new", MessagesNewHandler),
            (r"/message/updates", MessagesUpdatesHandler),
            (r"/logout", LogoutHandler),
            (r"/add/chatroom", AddChatroom),
            (r"/status", StatusHandler),
        ]
        
        settings = dict(
            cookie_secret=options.cookie_secret,
            template_path=os.path.join(os.path.dirname(__file__), options.template_dir),
            static_path=os.path.join(os.path.dirname(__file__), options.static_dir),
            xsrf_cookies=True,
        )
        Application.__init__(self, handlers, **settings)


def online_offline(room_id, user, on_off, **kwargs):
    '''
    当用户上下线的时候，通知对应房间内的用户
    当/post_new, /poll_message, /chat/xxxxx
    这三个URL被访问时，并判断用户是否已在线，发送online
    
    当关闭浏览器/标签的时候
    会导致关闭/poll_message连接，发送offline
    '''
    message = dict(
        user=user,
        on_off = on_off
    )
    
    if on_off == "online":
        message["remote_ip"] = kwargs.pop("remote_ip")
    
    room_waiters = redis.WaiterManager.get_waiters_for_room_id(room_id)
    try:
        for waiter in room_waiters:
            waiter(message, "online_offline")
    except Exception, e:
        LOG.exception(e)
    
    redis.WaiterManager.empty_waiter(room_id)
    LOG.warning("User %s has %s from room %s." % (user, on_off, room_id))


class WebHandler(RequestHandler):
    def compute_etag(self):
        return


class MainHandler(WebHandler):
    def get(self):
        self.render("index.html")


class LoginHandler(WebHandler):
    def get(self):
        user = self.get_secure_cookie("user")
        # 如果用户的cookie已经存在，则删除用户的欢迎标志
        # 当用户重新打开一个标签的时候，这种情况会发生
        redis.UserManager.del_user_welcome(user)
        
        self.render("login.html", user_exists=False)
    
    def post(self):
        username = self.get_argument("username")
        if not redis.UserManager.is_user_exists(username):
            self.set_secure_cookie("user", username)
            self.redirect("/room", status=301)
            return
        else:
            self.render("login.html", user_exists=True)
    

class LogoutHandler(WebHandler):
    def get(self):
        # delete user from userlist
        user = self.get_secure_cookie("user")
        redis.UserManager.user_del(user=user)
        redis.WaiterManager.remove_all_waiter(user)
        redis.UserManager.del_user_welcome(user)
        self.clear_cookie("user")
        self.render("logout.html", logout=True)


class AddChatroom(WebHandler):
    def get(self):
        room_name = self.get_argument("room_name")
        room_max_user = self.get_argument("room_max_user")
        # and chat room in local process and redis.
        room_id = redis.ChatroomManager.add_chat_room(room_name, room_max_user)
        # send "add_chatroom" to multicast channel.
        if room_id:
            ret = multicast_sender(redis.ChatroomManager.init_remote_chat_room(room_id), "command")
            if ret:
                self.write({"return": 0})
        else:
            self.send_error(500)


class ChatMain(WebHandler):
    @asynchronous
    def get(self, room_magic_id):
        self.room_id = redis.ChatroomManager.magic_2_normal(room_magic_id)
        if self.room_id and redis.ChatroomManager.check_room_id(self.room_id):
            user_list = redis.UserManager.get_room_user(self.room_id)
            
            self.user = self.get_secure_cookie("user")
            room_name = redis.ChatroomManager.get_room_name(self.room_id)
            
            online_offline(self.room_id, self.user, "online", remote_ip=self.request.remote_ip)
            
            # add user to userlist
            redis.UserManager.user_add(self.room_id, self.user, self)
            self.render("chat.html", user=self.user, user_list=user_list or None,
                        room_id=self.room_id, room_name=room_name,
                        messages=redis.MessageCacheManager.get_msg_for_room_id(self.room_id))


class MessageMixin(object):
    def wait_for_messages(self, callback, room_id, user, cursor=None):
        if cursor:
            index = 0
            msg_cache = redis.MessageCacheManager.get_msg_for_room_id(room_id)
            for i in xrange(len(msg_cache)):
                index = len(msg_cache) - i - 1
                if msg_cache[index]["id"] == cursor:
                    break
            
            recent = msg_cache[index + 1:]
            if recent:
                try:
                    callback(recent)
                except Exception, e:
                    LOG.error("Error in waiter callback", exc_info=True)
                    LOG.exception(e)
            
        redis.WaiterManager.add_waiter(callback, room_id, user)
    
    def cancel_wait(self, room_id, user):
        redis.WaiterManager.remove_waiter(room_id, user)
    
    def new_messages(self, messages, room_id):
        room_waiters = redis.WaiterManager.get_waiters_for_room_id(room_id)
        LOG.warning("Server sending new message to %r listeners" % len(room_waiters))
        for callback in room_waiters:
            try:
                callback(messages)
            except Exception, e:
                LOG.error("Error in waiter callback", exc_info=True)
                LOG.exception(e)
        
        redis.WaiterManager.empty_waiter(room_id)
        redis.MessageCacheManager.add_msg_cache(messages, room_id)
        
        # send messages to multicast channel
        multicast_sender(messages, "message")


class RoomList(WebHandler):
    def get(self):
        send_welcome = False
        user = self.get_secure_cookie("user")
        room_id = redis.lobby_room_id
        redis.UserManager.user_add(room_id, user, self)
        
        # if user login into lobby first time, send welcome message
        if redis.UserManager.user_welcome(user):
            message = {
                "id": str(uuid.uuid4()),
                "user": user,
                "time": time.strftime("%H:%M:%S"),
                "type":"welcome_message",
            }
            message['body'] = user
            message["html"] = self.render_string("message.html", message=message)
            room_waiters = redis.WaiterManager.get_waiters_for_room_id(room_id)
            for callback in room_waiters:
                try:
                    # 增加消息类型，让客户端js舍弃此次消息的id，而使用上次的
                    callback([message], "welcome_message")
                except Exception, e:
                    LOG.error("Error in waiter callback", exc_info=True)
                    LOG.exception(e)
            redis.WaiterManager.empty_waiter(room_id)
           
            multicast_sender(dict(user=user, message=[message]), "send_welcome")
            send_welcome = True
        
        server_time = from_now_to_datetime()
        self.render("room_list.html",
            user=user,
            send_welcome = send_welcome,
            server_time = server_time,
            room_id = room_id,
            room_list=redis.ChatroomManager.get_room_list(),
            messages=redis.MessageCacheManager.get_msg_for_room_id(room_id))


class MessagesNewHandler(WebHandler, MessageMixin):
    @asynchronous
    def post(self):
        room_id = self.get_argument("room_id")
        body = self.get_argument("body")
        msg_from = self.get_secure_cookie("user")
        
        # 当server重启后，server接收到client的新消息ajax请求
        # 发现用户不在线，则将用户加入到 userlist:room:x
        # 可以做到当server重启后，client依然能够自动接收到消息
        if not redis.UserManager.is_user_online(msg_from):
            redis.UserManager.user_add(room_id, msg_from, self)
            online_offline(room_id, msg_from, "online",
                           remote_ip=self.request.remote_ip)
            
        if not msg_from:
            self.finish({"status": "logout"})
            return
        
        msg_id = str(uuid.uuid4())
        message = {
            "id": msg_id,
            "from": msg_from,
            "body": body,
            "room_id": room_id,
            "time": time.strftime("%H:%M:%S"),
            "type":"normal_chat"
        }
        
        ########################## start command process ############################
        commander = CommandManager(body)
        if commander.is_command:
            ret = commander.analyst()
            
            # user to user chat
            if ret[0] == manager.USER_TO_USER_CHAT:
                user, user_message = ret[2], ret[3]
                
                # user is not online in current
                if not redis.UserManager.is_user_online(user):
                    message = {
                        "id": str(uuid.uuid4()),
                        "time": time.strftime("%H:%M:%S"),
                    }
                    message['type'] = "user_offline"
                    message["html"] = self.render_string("message.html", message=message)
                    self.finish(message)
                    return
                    
                user_waiters = redis.UserManager.is_local_user(user.encode('UTF-8'))
                message['type'] = "private_chat"
                message['body'] = user_message
                message["html"] = self.render_string("message.html", message=message)
                
                # if user on local process
                if user_waiters:
                    for waiter in user_waiters:
                        try:
                            waiter([message])
                        except Exception, e:
                            LOG.exception(e)
                # send message to multicast channel
                else:
                    multicast_sender(
                        dict(message=[message],
                            user=user),
                        "p2p_chat")
                
                # send feedback to user
                message.pop('body')
                message['type'] = "private_chat_sent"
                message["id"] = str(uuid.uuid4())
                message["html"] = self.render_string("message.html", message=message)
                self.finish(message)
                return
                
            # broadcast message
            elif ret[0] == manager.BROADCAST_CHAT:
                broadcast_message = ret[2]
                # send broadcast to local waiters
                waiters = redis.WaiterManager.get_all_local_waiter()
                message['type'] = "broadcast_chat"
                message['body'] = broadcast_message
                message["html"] = self.render_string("message.html", message=message)
                if waiters:
                    for waiter in waiters:
                        try:
                            waiter([message])
                        except Exception, e:
                            LOG.exception(e)
                
                # send broadcast to multicast channel
                multicast_sender(
                    dict(
                    message=[message]
                    ),
                    "broadcast")
                
                # send feedback to user
                message.pop('body')
                message["id"] = str(uuid.uuid4())
                message['type'] = "broadcast_sent"
                message["html"] = self.render_string("message.html", message=message)
                self.finish(message)
                return
            
            # check if user is online
            elif ret[0] == manager.CHECK_ONLINE:
                pass
            
            # admin kickoff user
            elif ret[0] == manager.KICKOFF_USER:
                pass
            
            # unknown command
            else:
                message = {
                    "id": str(uuid.uuid4()),
                    "time": time.strftime("%H:%M:%S"),
                }
                message['type'] = "command_error"
                message["html"] = self.render_string("message.html", message=message)
                self.finish(message)
                return
        ########################## end command process ############################
        
        message["html"] = self.render_string("message.html", message=message)
        # 在client post新消息后，只返回一个新消息的id
        # 以便client更新cursor，否则会造成消息重复
        self.write({"id": msg_id})
        self.finish()
        
        self.new_messages([message], room_id)
        return


class MessagesUpdatesHandler(WebHandler, MessageMixin):
    @asynchronous
    def post(self):
        self.room_id = self.get_argument("room_id")
        self.user = self.get_secure_cookie("user")
        # 当server重启后，server接收到client的自动ajax请求
        # 发现用户不在线，则将用户加入到 userlist:room:x
        # 可以做到当server重启后，client依然能够自动接收到消息
        if not redis.UserManager.is_user_online(self.user):
            redis.UserManager.user_add(self.room_id, self.user, self)
            online_offline(self.room_id, self.user,
                           "online", remote_ip=self.request.remote_ip)
            
        cursor = self.get_argument("cursor", None)
        self.wait_for_messages(self.on_new_messages, user=self.user,
                               cursor=cursor, room_id=self.room_id)
    
    def on_new_messages(self, messages, msg_type=None):
        if self.request.connection.stream.closed():
            return
        
        if not msg_type:
            message = dict(msg_type="normal", messages=messages)
        elif msg_type == "online_offline":
            message = dict(msg_type=msg_type, messages=messages)
        elif msg_type == "welcome_message":
            message = dict(msg_type=msg_type, messages=messages)
        
        self.finish(message)
        return
    
    def on_connection_close(self):
        # 2013/03/04 同一个用户在多个标签内，当其中一个标签关闭时
        # 不在某房间清除用户等待的链接，而是让发送新消息时自动清除
        # 并且在on_new_messages回调中有检测链接是否关闭
        # 所以可以检测到当连接关闭了还发送消息的情况退出
        # 这是因为在房间的room_waiter_list中
        # 以用户名为key以连接为value的键值对是惟一的
        # 同一个房间，打开多个标签，其中一个退出，会导致其他标签唯一的连接退出
        # self.cancel_wait(self.room_id, self.user)
        # delete user from userlist
        redis.UserManager.user_del(room_id=self.room_id, user=self.user)
        redis.UserManager.set_user_offline(self.user)
        online_offline(self.room_id, self.user, "offline")


class StatusHandler(WebHandler):
    def get(self):
        final_room_list = str(redis.room_list)
        room_list_detail = redis.UserManager.get_all_user_info()
        
        self.write(dict(
            local_room_list = final_room_list,
            room_list_detail = room_list_detail
        ))


#make current process goto daemon
def daemonize (stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    # Do first fork.
    try: 
        pid = os.fork() 
        if pid > 0:
            sys.exit(0)   # Exit first parent.
    except OSError, e: 
        sys.stderr.write ("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror) )
        sys.exit(1)

    # Decouple from parent environment.
    os.chdir(".") 
    os.umask(0) 
    os.setsid() 

    # Do second fork.
    try: 
        pid = os.fork() 
        if pid > 0:
            sys.exit(0)   # Exit second parent.
    except OSError, e: 
        sys.stderr.write ("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror) )
        sys.exit(1)

    # Now I am a daemon!
    
    # Redirect standard file descriptors.
    si = open(stdin, 'r')
    so = open(stdout, 'a+')
    se = open(stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


def server_stop():
    '''
    停止服务器并做一些清理工作
    '''
    ioloop.IOLoop.instance().stop()
    redis.SignalHandlerManager.on_server_exit()


def handler_signal(signum, frame):
    # if process receive SIGNINT/SITTERM/SIGQUIT
    # stop the server
    if signum == 2 or signum == 3 or signum ==15:
        LOG.error("Receive signal: %s" % signum)
        LOG.error("Server quit.")
        server_stop()
    elif signum == 14:  # ignore SIGALARM
        pass


signal.signal(signal.SIGTERM, handler_signal)
signal.signal(signal.SIGINT, handler_signal)
signal.signal(signal.SIGQUIT, handler_signal)
signal.signal(signal.SIGALRM, handler_signal)


def main(port):
    reload(sys)
    sys.setdefaultencoding('UTF-8')
    add_callback(multicast_receiver)
    app = iApplication()
    # xheaders=True
    # tronado运行在reverse proxy后面的时候获取client真实IP
    server = HTTPServer(app, xheaders=True)
    server.bind(port, family=socket.AF_INET)
    server.start()
    ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    tornado.options.parse_command_line()
    
    if options.daemon:
        daemonize()
    
    main(options.port)

