"""
游戏胜率统计查询命令
处理 /gamestats 和 /胜率 命令
"""
from pyrogram import filters
from bot import bot, prefixes, LOGGER
from bot.func_helper.msg_utils import sendMessage
from bot.func_helper.win_rate_stats import WinRateStatsManager


@bot.on_message(filters.command(['gamestats', '胜率'], prefixes=prefixes))
async def handle_gamestats_command(_, msg):
    """
    处理 /gamestats 和 /胜率 命令
    显示用户的游戏统计数据
    
    Args:
        _: Pyrogram 客户端（未使用）
        msg: 消息对象
    """
    user_id = msg.from_user.id
    username = msg.from_user.first_name
    
    # 查询用户统计数据
    stats = WinRateStatsManager.get_user_stats(user_id)
    
    # 格式化并发送统计消息
    message = WinRateStatsManager.format_stats_message(stats, username)
    await sendMessage(msg, message)
    
    LOGGER.info(f"用户 {username}({user_id}) 查询了游戏统计")
