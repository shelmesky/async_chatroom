#!/usr/bin/python
# -- encoding:utf-8 --


__all__ = ["USER_TO_USER_CHAT", "BROADCAST_CHAT",
          "CHECK_ONLINE", "CommandManager", "KICKOFF_USER"]

USER_TO_USER_CHAT = 1
BROADCAST_CHAT = 2
CHECK_ONLINE = 3
KICKOFF_USER = 4


class CommandManager(object):
    def __init__(self, body):
        self.body = body.strip()
    
    @property
    def is_command(self):
        if self.body[0] == '/' and len(self.body) > 1:
            return True
        else:
            return False
    
    def analyst(self):
        result = self.body.split(' ')
        try:
            cmd = result[0][1:]
            if cmd == "chat":
                user = result[1]
                message = " ".join(result[2:])
                return (USER_TO_USER_CHAT, cmd,
                        user, message, )
            
            elif cmd == "bc":
                message = " ".join(result[1:])
                return (BROADCAST_CHAT,
                        cmd, message, )
            
            elif cmd == "online":
                users = result[1:]
                return (CHECK_ONLINE,
                        cmd, users, )
            
            elif cmd == "kickoff":
                users = result[1:]
                return (KICKOFF_USER,
                        cmd, users, )
            
            else:
                return (False, )
        except Exception, e:
            return (False, )

