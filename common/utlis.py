# --encoding:utf-8--

import datetime

def from_now_to_datetime(time_format=None, **kwargs):
    '''
    计算从现在开始到某一个时间，返回格式化之后的时间字符串
    days = 1 一天之后
    seconds = 60 60秒之后
    time_format = None 格式化参数，默认为: %Y-%m-%d %H:%M:%S
    不带参数调用则输出当前时间的格式化字符串
    '''
    if not time_format:
        time_format = "%Y-%m-%d %H:%M:%S"
    days = kwargs.get("days", 0)
    seconds = kwargs.get("seconds", 0)
    now = datetime.datetime.now()
    result = now + datetime.timedelta(days=days, seconds=seconds)
    return result.strftime(time_format)

