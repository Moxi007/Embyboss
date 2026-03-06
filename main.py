#! /usr/bin/python3
# -*- coding: utf-8 -*-

from bot import bot

# 面板
from bot.modules.panel import *
# 命令
from bot.modules.commands import *
# 其他
from bot.modules.extra import *
from bot.modules.callback import *
from bot.web import *

import asyncio

if __name__ == '__main__':
    from bot.func_helper.registration_queue import queue_worker, WORKER_COUNT
    
    # 获取 pyrogram 绑定的当前事件循环
    loop = asyncio.get_event_loop()
    
    # 启动多个后台常驻消费队列 Worker（并行处理注册请求）
    for i in range(WORKER_COUNT):
        loop.create_task(queue_worker(worker_id=i))
    
    # 启动机器人
    bot.run()
