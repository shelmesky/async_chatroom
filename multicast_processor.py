import simplejson as json

from backend.redis import redis_backend as redis
from backend.multicast.sender import sender
from common.encrypter import crypter
from common.logger import LOG


def multicast_processor(conn, local_node_id=None):
    data, address = conn.recvfrom(1024)
    data = crypter.decrypt(data)
    data = eval(data)
    remote_node_id = data['node_id']
    msg_type = data['msg_type']
    body = data['body']
    
    if remote_node_id != local_node_id:
        
        if msg_type == "message":
            room_id = body[0]['room_id']
            waiters = redis.WaiterManager.get_waiters_for_room_id(room_id)
            if waiters:
                for waiter in waiters:
                    try:
                        waiter(body)
                    except Exception, e:
                        LOG.exception(e)
                redis.WaiterManager.empty_waiter(room_id)
                LOG.warning("Receive [normal chat] message and send to %r listeners." % len(waiters))
        
        elif msg_type == "command":
            cmd = body['cmd']
            if "add_chatroom" == cmd:
                room_id = body['room_id']
                if redis.ChatroomManager.add_local_chat_room(room_id):
                    LOG.warning("Receive command add chat room %d." % room_id)
                    
            elif "del_chatroom" == cmd:
                pass
        
        elif msg_type == "p2p_chat":
            user = body['user']
            message = body['message']
            user_waiters = redis.UserManager.is_local_user(user.encode('utf-8'))
            if user_waiters:
                for waiter in user_waiters:
                    try:
                        waiter(message)
                    except Exception, e:
                        LOG.exception(e)
                LOG.warning("Receive [p2p] message and send to %s listeners." % user)
        
        elif msg_type == "broadcast":
            message = body['message']
            waiters = redis.WaiterManager.get_all_local_waiter()
            for waiter in waiters:
                try:
                    waiter(message)
                except Exception, e:
                    LOG.exception(e)
            LOG.warning("Receive [broadcast] message and send to %s listeners." % len(waiters))
        
        elif msg_type == "send_welcome":
            message = body['message']
            waiters = redis.WaiterManager.get_all_local_waiter()
            for waiter in waiters:
                try:
                    waiter(message)
                except Exception, e:
                    LOG.exception(e)
            LOG.warning("Receive [welcome] message and send to %s listeners." % len(waiters))


def multicast_sender(messages, msg_type, local_node_id=None):
    """
    Send message to multicast channel.
    messages: message need to send.
    msg_type: type of message, can be "message" or "command".
    """
    msg = dict(
        node_id = local_node_id,
        msg_type = msg_type,
        body = messages
    )
    msg = str(msg)
    msg = crypter.encrypt(msg)
    try:
        if sender(msg):
            LOG.warning("Send %d to multicast channel." % len(messages))
    except Exception, e:
        return False
    return True

