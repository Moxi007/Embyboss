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
    
    支持两种查询方式：
    1. 直接使用命令：查询自己的胜率
    2. 回复别人的消息使用命令：查询被回复者的胜率
    
    Args:
        _: Pyrogram 客户端（未使用）
        msg: 消息对象
    """
    # 确定要查询的用户
    if msg.reply_to_message:
        # 回复消息时查询被回复者
        target_user_id = msg.reply_to_message.from_user.id
        target_username = msg.reply_to_message.from_user.first_name
    else:
        # 没有回复时查询自己
        target_user_id = msg.from_user.id
        target_username = msg.from_user.first_name
    
    # 创建用户名链接（可点击跳转到用户主页）
    username_link = f"[{target_username}](tg://user?id={target_user_id})"
    
    # 查询用户统计数据
    stats = WinRateStatsManager.get_user_stats(target_user_id)
    
    # 格式化并发送统计消息
    message = WinRateStatsManager.format_stats_message(stats, username_link)
    await sendMessage(msg, message)
    
    LOGGER.info(f"用户 {msg.from_user.first_name}({msg.from_user.id}) 查询了 {target_username}({target_user_id}) 的游戏统计")


@bot.on_message(filters.command(['wintop', '胜率榜'], prefixes=prefixes))
async def handle_leaderboard_command(_, msg):
    """
    处理 /wintop 和 /胜率榜 命令
    显示游戏胜率排行榜
    
    Args:
        _: Pyrogram 客户端（未使用）
        msg: 消息对象
    """
    # 查询排行榜数据
    leaderboard = WinRateStatsManager.get_win_rate_leaderboard(limit=10)
    
    # 格式化并发送排行榜消息
    message = WinRateStatsManager.format_leaderboard_message(leaderboard)
    await sendMessage(msg, message)
    
    LOGGER.info(f"用户 {msg.from_user.first_name}({msg.from_user.id}) 查询了胜率排行榜")
