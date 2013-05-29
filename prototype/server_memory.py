#!/usr/bin/python
# --encoding: utf-8 --

import os
import sys
import simplejson as json
import random
import uuid
import logging

from tornado.web import RequestHandler
from tornado.web import Application
from tornado.web import asynchronous
from tornado import ioloop

from backend.memory import backend_memory as memory


class iApplication(Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/room_list", RoomList),
            (r"/room/([0-9]+)", RoomEnter),
            (r"/chat", ChatMain),
            (r"/message/new", MessagesNewHandler),
            (r"/message/updates", MessagesUpdatesHandler),
            (r"/logout", LogoutHandler),
            (r"/add/chatroom", AddChatroom),
        ]
        
        settings = dict(
            cookie_secret="as897f293(*&^*%l1243j@#%(^%sf882983",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=True,
        )
        Application.__init__(self, handlers, **settings)


class MainHandler(RequestHandler):
    def get(self):
        random_str = str(random.randint(1000000, 99999999))
        self.set_secure_cookie("user","user-" + random_str)
        self.redirect("/room_list")


class LogoutHandler(RequestHandler):
    def get(self):
        self.clear_cookie("user")
        self.clear_cookie("room_id")
        self.render("logout.html", logout=True)


class AddChatroom(RequestHandler):
    def get(self):
        room_name = self.get_argument("room_name")
        room_max_user = self.get_argument("room_max_user")
        if memory.add_chat_room(room_name, room_max_user):
            self.write("Add chat room successfully!")


class ChatMain(RequestHandler):
    def get(self):
        user = self.get_secure_cookie("user")
        room_id = self.get_secure_cookie("room_id")
        room_name = memory.get_room_name(room_id)
        self.render("chat.html", user=user,
                    room_id=room_id, room_name=room_name,
                    messages=memory.get_msg_for_room_id(room_id))


class RoomEnter(RequestHandler):
    def get(self, room_id):
        if memory.check_room_id(room_id):
            cookie = self.set_secure_cookie("room_id", room_id)
            self.redirect("/chat")
        else:
            self.write("Room does not exists.")


class MessageMixin(object):
    def wait_for_messages(self, callback, room_id, cursor=None):
        if cursor:
            index = 0
            msg_cache = memory.get_msg_for_room_id(room_id)
            for i in xrange(len(msg_cache)):
                index = len(msg_cache) - i - 1
                if msg_cache[index]["id"] == cursor:
                    break
            
            recent = msg_cache[index + 1:]
            if recent:
                callback(recent)
                return
            
        memory.add_waiter(callback, room_id)
    
    def cancel_wait(self, callback, room_id):
        memory.remove_waiter(callback, room_id)
    
    # 从chat_room channel来的消息，也会调用这个方法
    def new_messages(self, messages, room_id):
        room_waiters = memory.get_waiters_for_room_id(room_id)
        print("Sending new message to %r listeners" % len(room_waiters))
        for callback in room_waiters:
            try:
                callback(messages)
            except:
                logging.error("Error in waiter callback", exc_info=True)
        
        memory.empty_waiter(room_id)
        memory.add_msg_cache(messages, room_id)


class RoomList(RequestHandler):
    def get(self):
        self.render("room_list.html", room_list=memory.get_room_list())


class MessagesNewHandler(RequestHandler, MessageMixin):
    def post(self):
        room_id = self.get_secure_cookie("room_id")
        message = {
            "id": str(uuid.uuid4()),
            "from": self.get_secure_cookie("user"),
            "body": self.get_argument("body"),
            "room_id": self.get_argument("room_id"),
        }
        message["html"] = self.render_string("message.html", message=message)
        self.write(message)
        self.new_messages([message], room_id)


class MessagesUpdatesHandler(RequestHandler, MessageMixin):
    @asynchronous
    def post(self):
        self.room_id = self.get_secure_cookie("room_id")
        cursor = self.get_argument("cursor", None)
        self.wait_for_messages(self.on_new_messages,
                               cursor=cursor, room_id=self.room_id)
    
    def on_new_messages(self, messages):
        if self.request.connection.stream.closed():
            return
        self.finish(dict(messages=messages))
        return
    
    def on_connection_close(self):
        self.cancel_wait(self.on_new_messages, self.room_id)


def main():
    app = iApplication()
    app.listen("9999")
    ioloop.IOLoop.instance().start()


if __name__ == '__main__':
    main()

