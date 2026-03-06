import asyncio
from bot import LOGGER, bot
from pyrogram.types import CallbackQuery

# 全局注册请求队列
registration_queue = asyncio.Queue()

# 去重集合：防止同一用户重复入队
_pending_users = set()

# Worker 数量配置
WORKER_COUNT = 3


def is_user_pending(tg_id: int) -> bool:
    """检查用户是否已在注册队列中"""
    return tg_id in _pending_users


def add_pending_user(tg_id: int):
    """标记用户已入队"""
    _pending_users.add(tg_id)


def remove_pending_user(tg_id: int):
    """移除用户的入队标记"""
    _pending_users.discard(tg_id)


async def queue_worker(worker_id: int = 0):
    """
    后台常驻任务：匀速消费注册队列中的请求，防止瞬间并发压垮数据库。
    支持多 Worker 并行消费，通过 asyncio.Queue 天然线程安全分发。
    """
    LOGGER.info(f"🚀 注册队列 Worker-{worker_id} 已启动...")
    while True:
        try:
            # 阻塞等待队列中的任务
            task_data = await registration_queue.get()
            tg_id, us, stats, call = task_data

            LOGGER.info(f"⏳ Worker-{worker_id} 正在处理注册请求: 用户ID {tg_id}")

            # 引入实际的注册逻辑
            from bot.modules.panel.member_panel import create_user

            await create_user(None, call, us=us, stats=stats, is_queued=True)

            # 标记任务完成并清除去重标记
            registration_queue.task_done()
            remove_pending_user(tg_id)

            # 消费速率：每个 Worker 处理完一个后等待 0.05 秒
            # 3 个 Worker 理论峰值 ≈ 60 注册/秒
            await asyncio.sleep(0.05)

        except asyncio.CancelledError:
            LOGGER.info(f"⏹️ 注册队列 Worker-{worker_id} 被取消/关闭。")
            break
        except Exception as e:
            LOGGER.error(f"❌ Worker-{worker_id} 处理注册任务异常: {e}")
            # 出错时也要清除去重标记和标记任务完成，否则队列计数器会漂移
            try:
                registration_queue.task_done()
                remove_pending_user(tg_id)
            except:
                pass
            # 通知用户注册失败，让其重试
            try:
                await bot.send_message(tg_id, "❌ **注册出现异常，请稍后重新点击注册按钮重试。**")
            except:
                pass
            await asyncio.sleep(0.5)
