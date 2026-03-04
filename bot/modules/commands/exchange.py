"""
兑换注册码exchange
"""
from datetime import timedelta, datetime

from bot import LOGGER, bot, config
from bot.func_helper.emby import emby
from bot.func_helper.fix_bottons import register_code_ikb
from bot.func_helper.msg_utils import sendMessage, sendPhoto
from bot.sql_helper.sql_code import Code
from bot.sql_helper.sql_emby import sql_get_emby, Emby
from bot.sql_helper import Session
from sqlalchemy import select, update
from pyrogram.errors import PeerIdInvalid


def is_renew_code(input_string):
    if "Renew" in input_string:
        return True
    else:
        return False


async def rgs_code(_, msg, register_code, passed_captcha=False):
    if config.open.stat:
        return await sendMessage(msg, "🤧 自由注册开启下无法使用注册码。")

    if not passed_captcha:
        from bot.func_helper.captcha import generate_math_captcha
        user_id = msg.from_user.id
        question, keyboard = generate_math_captcha(user_id, "rgs_code", {"code": register_code})
        await sendMessage(msg, f"🤖 **防机器人验证**\n请计算以下算式并选择正确答案（倒计时 120s）：\n\n**{question}**", buttons=keyboard, send=True)
        return

    data = await sql_get_emby(tg=msg.from_user.id)
    if not data:
        return await sendMessage(msg, "出错了，不确定您是否有资格使用，请先 /start")
    embyid = data.embyid
    ex = data.ex
    lv = data.lv
    if embyid:
        if not is_renew_code(register_code):
            return await sendMessage(msg, "🔔 很遗憾，您使用的是注册码，无法启用续期功能，请悉知", timer=60)
        async with Session() as session:
            # with_for_update 锁定当前行确保不会被其他并发进程读取
            stmt = select(Code).filter(Code.code == register_code).with_for_update()
            result = await session.execute(stmt)
            r = result.scalars().first()
            if not r:
                return await sendMessage(msg, "⛔ **你输入了一个错误de续期码，请确认好重试。**", timer=60)
            
            stmt_update = update(Code).where(Code.code == register_code, Code.used.is_(None)).values(
                used=msg.from_user.id, usedtime=datetime.now()
            )
            re_result = await session.execute(stmt_update)
            re = re_result.rowcount
            await session.commit()
            tg1 = r.tg
            us1 = r.us
            used = r.used
            if re == 0: 
                return await sendMessage(msg, f'此 `{register_code}` \n续期码已被使用,是[{used}](tg://user?id={used})的形状了喔')
            
            # 更新本身不用再重复一次因为上一步就是保证如果未使用才能更新
            try:
                first = await bot.get_chat(tg1)
                first_name = first.first_name
            except (PeerIdInvalid, Exception):
                first_name = f"用户({tg1})"
            # 此处需要写一个判断 now和ex的大小比较。进行日期加减。
            ex_new = datetime.now()
            if ex_new > ex:
                ex_new = ex_new + timedelta(days=us1)
                await emby.emby_change_policy(emby_id=embyid, disable=False)
                if lv == 'c':
                    await session.execute(update(Emby).where(Emby.tg == msg.from_user.id).values(ex=ex_new, lv='b'))
                else:
                    await session.execute(update(Emby).where(Emby.tg == msg.from_user.id).values(ex=ex_new))
                await sendMessage(msg, f'🎊 少年郎，恭喜你，已收到 [{first_name}](tg://user?id={tg1}) 的{us1}天🎁\n'
                                       f'__已解封账户并延长到期时间至(以当前时间计)__\n到期时间：{ex_new.strftime("%Y-%m-%d %H:%M:%S")}')
            elif ex_new < ex:
                ex_new = data.ex + timedelta(days=us1)
                await session.execute(update(Emby).where(Emby.tg == msg.from_user.id).values(ex=ex_new))
                await sendMessage(msg, f'🎊 少年郎，恭喜你，已收到 [{first_name}](tg://user?id={tg1}) 的{us1}天🎁\n到期时间：{ex_new}__')
            await session.commit()
            new_code = register_code[:-7] + "░" * 7
            await sendMessage(msg,
                              f'· 🎟️ 续期码使用 - [{msg.from_user.first_name}](tg://user?id={msg.chat.id}) [{msg.from_user.id}] 使用了 {new_code}\n· 📅 实时到期 - {ex_new}',
                              send=True)
            LOGGER.info(f"【续期码】：{msg.from_user.first_name}[{msg.chat.id}] 使用了 {register_code}，到期时间：{ex_new}")

    else:
        if is_renew_code(register_code):
            return await sendMessage(msg, "🔔 很遗憾，您使用的是续期码，无法启用注册功能，请悉知", timer=60)
        if data.us > 0:
            return await sendMessage(msg, "已有注册资格，请先使用【创建账户】注册，勿重复使用其他注册码。")
        async with Session() as session:
            # 原子操作 + 排他锁 成功防止了并发更新
            stmt = select(Code).filter(Code.code == register_code).with_for_update()
            result = await session.execute(stmt)
            r = result.scalars().first()
            if not r:
                return await sendMessage(msg, "⛔ **你输入了一个错误de注册码，请确认好重试。**")
            code_prefix = register_code.split('-')[0]
            # 判断此注册码使用者为管理员赠送的tg, 如果不是则拒绝使用
            if code_prefix not in config.ranks.logo and code_prefix != str(msg.from_user.id):
                return await sendMessage(msg, '🤺 你也想和bot击剑吗 ?', timer=60)
            
            stmt_update = update(Code).where(Code.code == register_code, Code.used.is_(None)).values(
                used=msg.from_user.id, usedtime=datetime.now()
            )
            re_result = await session.execute(stmt_update)
            re = re_result.rowcount
            await session.commit()
            tg1 = r.tg
            us1 = r.us
            used = r.used
            if re == 0: 
                return await sendMessage(msg, f'此 `{register_code}` \n注册码已被使用,是 [{used}](tg://user?id={used}) 的形状了喔')
            try:
                first = await bot.get_chat(tg1)
                first_name = first.first_name
            except (PeerIdInvalid, Exception):
                first_name = f"用户({tg1})"
            x = data.us + us1
            await session.execute(update(Emby).where(Emby.tg == msg.from_user.id).values(us=x))
            await session.commit()
            await sendPhoto(msg, photo=config.bot_photo,
                            caption=f'🎊 少年郎，恭喜你，已经收到了 [{first_name}](tg://user?id={tg1}) 发送的邀请注册资格\n\n请选择你的选项~',
                            buttons=register_code_ikb)
            new_code = register_code[:-7] + "░" * 7
            await sendMessage(msg,
                              f'· 🎟️ 注册码使用 - [{msg.from_user.first_name}](tg://user?id={msg.chat.id}) [{msg.from_user.id}] 使用了 {new_code}',
                              send=True)
            LOGGER.info(
                f"【注册码】：{msg.from_user.first_name}[{msg.chat.id}] 使用了 {register_code} - {us1}")

# @bot.on_message(filters.regex('exchange') & filters.private & user_in_group_on_filter)
# async def exchange_buttons(_, call):
#
#     await rgs_code(_, msg)
