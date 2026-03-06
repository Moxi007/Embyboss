import asyncio
from bot import LOGGER, bot
from pyrogram.types import CallbackQuery

# 全局注册请求队列
registration_queue = asyncio.Queue()

async def queue_worker():
    """
    后台常驻任务：匀速消费注册队列中的请求，防止瞬间并发压垮数据库。
    """
    LOGGER.info("🚀 注册异步处理队列 Worker 已启动...")
    while True:
        try:
            # 阻塞等待队列中的任务
            task_data = await registration_queue.get()
            tg_id, us, stats, call = task_data
            
            LOGGER.info(f"⏳ 正在处理队列中的注册请求: 用户ID {tg_id}")
            
            # 引入实际的注册逻辑
            from bot.func_helper.emby import create_user
            
            # 因为 create_user 原版依赖 call 对象进行 editMessage
            # 我们在后台调用它时，仍然传入原始 call。但如果超时，editMessage 可能会失败。
            # 这是正常现象，因为我们已经在加入队列前给 call 回复过 "排队中" 提示。
            await create_user(None, call, us=us, stats=stats, is_queued=True)
            
            # 标记任务完成
            registration_queue.task_done()
            
            # 消费限速，每处理一个注册请求，强制等待 0.2 秒（即每秒最多处理 5 个注册请求）
            # 这可以完全化解几千人并发时的查库写库高峰
            await asyncio.sleep(0.2)
            
        except asyncio.CancelledError:
            LOGGER.info("⏹️ 注册处理队列 Worker 被取消/关闭。")
            break
        except Exception as e:
            LOGGER.error(f"❌ 处理注册队列任务时发生异常: {e}")
            await asyncio.sleep(1) # 出错时稍微休眠防死循环
