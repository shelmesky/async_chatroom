# --encoding:utf-8--


# max message cache size for each chat room
msg_cache_size = 200

room_list = []

# settings for default chat room
default_room = {
    'room_id':1,
    'room_name':'Default Room',
    'room_waiter_list': set(),  # waiters in this chat room must be unique
    'room_msg_cache': list(),   # the msg in cache can be duplicate
    'room_max_user': 100,       # max user in this chat room
}
room_list.append(default_room)


def add_chat_room(room_name, room_max_user):
    """
    add a chat room
    room_name: name
    room_max_user: max user for this chat room
    """
    if room_name and room_max_user:
        try:
            room_max_user = int(room_max_user)
        except Exception, e:
            print("the parameter 'room_max_user' is not a digist!")
            return False
        room_id_list = list()
        for room in room_list:
            room_id_list.append(room['room_id'])
        max_room_id = max(room_id_list) + 1
        custom_room = dict(
            room_id = max_room_id,
            room_name = room_name,
            room_waiter_list = set(),
            room_msg_cache = list(),
            room_max_user = room_max_user
        )
        room_list.append(custom_room)
        return True


def add_msg_cache(messages, room_id):
    """
    add message to message cache for the room
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            room_msg_cache = room['room_msg_cache']
            room_msg_cache.extend(messages)
            if len(room_msg_cache) > msg_cache_size:
                room_msg_cache = room_msg_cache[-msg_cache_size]


def add_waiter(callback, room_id):
    """
    add suspended callback(client) for the room
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            room['room_waiter_list'].add(callback)


def empty_waiter(room_id):
    """
    clear all the suspended callback(client) for the room
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            room['room_waiter_list'] = set()


def remove_waiter(callback, room_id):
    """
    delete a suspended callback(client) for a room
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            room['room_waiter_list'].remove(callback)


def get_msg_for_room_id(room_id):
    """
    get all the message cache for the room
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            return room['room_msg_cache']


def get_waiters_for_room_id(room_id):
    """
    get all the suspended callback(client) for the room in a list
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            return room['room_waiter_list']


def get_room_list():
    """
    get information for all the room
    """
    lists = list()
    for room in room_list:
        temp = dict()
        temp['room_id'] = room['room_id']
        temp['room_name'] = room['room_name']
        temp['room_waiter_list'] = list(room['room_waiter_list'])
        lists.append(temp)
    return lists


def check_room_id(room_id):
    """
    check if the room id is existed
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            return True


def get_room_name(room_id):
    """
    get the room name by room id
    """
    for room in room_list:
        if int(room_id) == room['room_id']:
            return room['room_name']


def check_max_user(room_id):
    """
    check the max user of a room
    """
    pass
