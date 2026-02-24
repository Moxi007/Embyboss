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
    
    支持三种查询方式：
    1. 直接使用命令：查询自己的胜率
    2. /gamestats <tgid>：查询指定用户ID的胜率
    3. 回复别人的消息使用命令：查询被回复者的胜率
    
    优先级：回复消息 > 命令参数 > 自己
    
    Args:
        _: Pyrogram 客户端（未使用）
        msg: 消息对象
    """
    # 确定要查询的用户
    if msg.reply_to_message:
        # 回复消息时查询被回复者（优先级最高）
        target_user_id = msg.reply_to_message.from_user.id
        target_username = msg.reply_to_message.from_user.first_name
    elif len(msg.command) > 1:
        # 有参数时查询指定用户
        try:
            target_user_id = int(msg.command[1])
            # 需要查询数据库获取用户名
            from bot.sql_helper.sql_emby import sql_get_emby
            user = sql_get_emby(target_user_id)
            target_username = user.name if user and user.name else "未知用户"
        except (ValueError, AttributeError):
            await sendMessage(msg, "❌ 无效的用户ID")
            return
    else:
        # 默认查询自己
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
    
    支持分页：/wintop 或 /wintop <页码>
    每页显示 10 个玩家
    
    Args:
        _: Pyrogram 客户端（未使用）
        msg: 消息对象
    """
    # 解析页码参数
    page = 1
    if len(msg.command) > 1:
        try:
            page = int(msg.command[1])
            if page < 1:
                page = 1
        except ValueError:
            await sendMessage(msg, "❌ 无效的页码")
            return
    
    # 查询所有符合条件的玩家（至少参与 5 局）
    all_players = WinRateStatsManager.get_win_rate_leaderboard(limit=None)
    
    if not all_players:
        await sendMessage(msg, "🏆 胜率排行榜\n\n暂无排行数据（需至少参与 5 局游戏）")
        return
    
    # 计算分页
    import math
    page_size = 10
    total_pages = math.ceil(len(all_players) / page_size)
    
    # 确保页码在有效范围内
    if page > total_pages:
        page = total_pages
    
    # 获取当前页数据
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_players = all_players[start_idx:end_idx]
    
    # 格式化并发送排行榜消息
    message = WinRateStatsManager.format_leaderboard_message(page_players, page, total_pages, start_idx)
    
    # 添加分页按钮
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    
    # 上一页按钮
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"wintop:{page-1}"))
    
    # 下一页按钮
    if page < total_pages:
        buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"wintop:{page+1}"))
    
    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
    
    await sendMessage(msg, message, buttons=keyboard)
    
    LOGGER.info(f"用户 {msg.from_user.first_name}({msg.from_user.id}) 查询了胜率排行榜（第 {page} 页）")



@bot.on_callback_query(filters.regex('^wintop:'))
async def handle_leaderboard_page(_, call):
    """
    处理排行榜分页按钮点击
    
    Args:
        _: Pyrogram 客户端（未使用）
        call: 回调查询对象
    """
    from bot.func_helper.msg_utils import editMessage, callAnswer
    
    # 解析页码
    page = int(call.data.split(':')[1])
    await callAnswer(call, f'🔍 打开第 {page} 页')
    
    # 查询所有符合条件的玩家
    all_players = WinRateStatsManager.get_win_rate_leaderboard(limit=None)
    
    if not all_players:
        await editMessage(call, "🏆 胜率排行榜\n\n暂无排行数据（需至少参与 5 局游戏）")
        return
    
    # 计算分页
    import math
    page_size = 10
    total_pages = math.ceil(len(all_players) / page_size)
    
    # 确保页码在有效范围内
    if page > total_pages:
        page = total_pages
    if page < 1:
        page = 1
    
    # 获取当前页数据
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    page_players = all_players[start_idx:end_idx]
    
    # 格式化排行榜消息
    message = WinRateStatsManager.format_leaderboard_message(page_players, page, total_pages, start_idx)
    
    # 添加分页按钮
    from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    
    # 上一页按钮
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ 上一页", callback_data=f"wintop:{page-1}"))
    
    # 下一页按钮
    if page < total_pages:
        buttons.append(InlineKeyboardButton("➡️ 下一页", callback_data=f"wintop:{page+1}"))
    
    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None
    
    await editMessage(call, message, buttons=keyboard)
    
    LOGGER.info(f"用户 {call.from_user.first_name}({call.from_user.id}) 查看了胜率排行榜（第 {page} 页）")
