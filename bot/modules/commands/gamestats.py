"""
游戏胜率统计查询命令
处理 /win 和 /胜率 命令
"""
from pyrogram import filters, enums
from pyrogram.enums import ParseMode
from bot import bot, prefixes, LOGGER
from bot.func_helper.msg_utils import sendMessage
from bot.func_helper.win_rate_stats import WinRateStatsManager


@bot.on_message(filters.command(['win', '胜率'], prefixes=prefixes))
async def handle_gamestats_command(_, msg):
    """
    处理 /win 和 /胜率 命令
    显示用户的游戏统计数据
    
    支持三种查询方式：
    1. 直接使用命令：查询自己的胜率
    2. /win <tgid>：查询指定用户ID的胜率
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
        # 有参数时查询指定用户（异步场景）
        try:
            target_user_id = int(msg.command[1])
            # 通过 get_users() 获取 Telegram 用户名字典
            from bot.func_helper.utils import get_users
            members_dict = await get_users()
            # 使用 Telegram 用户名，无法获取时降级显示 Telegram ID
            target_username = members_dict.get(target_user_id, target_user_id)
        except (ValueError, AttributeError):
            await sendMessage(msg, "❌ 无效的用户ID")
            return
    else:
        # 默认查询自己
        target_user_id = msg.from_user.id
        target_username = msg.from_user.first_name
    
    # 创建用户名链接（可点击跳转到用户主页）
    import re
    # 暴力删除所有非中文、非英文字母、非数字的字符
    clean_username = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', str(target_username))
    username_link = f"[{clean_username}](tg://user?id={target_user_id})"
    
    # 查询用户统计数据
    stats = WinRateStatsManager.get_user_stats(target_user_id)
    
    # 格式化并发送统计消息（不传 parse_mode 默认解析 Markdown）
    message = WinRateStatsManager.format_stats_message(stats, username_link)
    await sendMessage(msg, message)
    
    LOGGER.info(f"用户 {msg.from_user.first_name}({msg.from_user.id}) 查询了 {target_username}({target_user_id}) 的游戏统计")


@bot.on_message(filters.command(['wintop', '胜率榜'], prefixes=prefixes))
async def handle_leaderboard_command(_, msg):
    """处理 /wintop 和 /胜率榜 命令"""
    import asyncio
    from bot.func_helper.fix_bottons import win_rate_button
    from bot.func_helper.msg_utils import sendPhoto
    from bot import bot_photo
    
    sender = msg.from_user.id if not msg.sender_chat else msg.sender_chat.id
    
    reply = await msg.reply("请稍等......加载中")
    pages_text, total_pages = await WinRateStatsManager.get_win_rate_rank_pages()
    
    if not pages_text:
        await reply.edit("🏆 胜率排行榜\n\n暂无排行数据")
        return
    
    button = await win_rate_button(total_pages, 1, sender)
    
    await asyncio.gather(
        reply.delete(),
        sendPhoto(
            msg,
            photo=bot_photo,
            caption=f"<b>▎🏆 胜率排行榜</b>\n\n{pages_text[0]}",
            buttons=button,
            parse_mode=ParseMode.HTML  # 使用 HTML 解析以确保链接生效
        ),
    )


@bot.on_callback_query(filters.regex('^win_rate:'))
async def handle_win_rate_page(_, call):
    """处理排行榜翻页"""
    from bot.func_helper.msg_utils import callAnswer, editMessage
    from bot.func_helper.fix_bottons import win_rate_button
    from bot.func_helper.utils import judge_admins
    
    j, tg = map(int, call.data.split(":")[1].split("_"))
    
    if call.from_user.id != tg:
        if not judge_admins(call.from_user.id):
            return await callAnswer(
                call, "❌ 这不是你召唤出的榜单，请使用自己的 /wintop", True
            )
    
    await callAnswer(call, f"将为您翻到第 {j} 页")
    
    pages_text, total_pages = await WinRateStatsManager.get_win_rate_rank_pages()
    button = await win_rate_button(total_pages, j, tg)
    text = pages_text[j - 1]
    
    await editMessage(
        call, 
        f"<b>▎🏆 胜率排行榜</b>\n\n{text}",
        buttons=button,
        parse_mode=ParseMode.HTML  # 同样指定为 HTML
    )