"""
用户区面板代码
先检测有无账户
无 -> 创建账户、换绑tg

有 -> 账户续期，重置密码，删除账户，显隐媒体库
"""
import asyncio
import datetime
import math
import random
from datetime import timedelta, datetime
from bot.schemas import ExDate, Yulv
from bot import LOGGER, bot, config
from pyrogram import filters
from bot.func_helper.emby import emby
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.utils import members_info, tem_adduser, cr_link_one, judge_admins, tem_deluser, pwd_create
from bot.func_helper.fix_bottons import members_ikb, back_members_ikb, re_create_ikb, del_me_ikb, re_delme_ikb, \
    re_reset_ikb, re_changetg_ikb, emby_block_ikb, user_emby_block_ikb, user_emby_unblock_ikb, re_exchange_b_ikb, \
    store_ikb, re_bindtg_ikb, close_it_ikb, store_query_page, re_born_ikb, send_changetg_ikb, favorites_page_ikb
from bot.func_helper.msg_utils import callAnswer, editMessage, callListen, sendMessage, ask_return, deleteMessage
from bot.modules.commands import p_start
from bot.modules.commands.exchange import rgs_code
from bot.sql_helper.sql_code import sql_count_c_code
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby, sql_delete_emby
from bot.sql_helper.sql_emby2 import sql_get_emby2, sql_delete_emby2

# 添加全局锁
_create_user_lock = asyncio.Lock()

# 创号函数
async def create_user(_, call, us, stats, is_queued=False):
    msg = await ask_return(call,
                           text='🤖**注意：您已进入排队注册流程:\n\n• 请在2min内输入 `[用户名][空格][安全码]`\n• 举个例子🌰：`苏苏 1234`**\n\n• 用户名中不限制中/英文/emoji，🚫**特殊字符**'
                                '\n• 安全码为敏感操作时附加验证，请填入最熟悉的数字4~6位；退出请点 /cancel', timer=120,
                           button=close_it_ikb)
    if not msg:
        return

    elif msg.text == '/cancel':
        return await asyncio.gather(msg.delete(), bot.delete_messages(msg.from_user.id, msg.id - 1))

    try:
        emby_name, emby_pwd2 = msg.text.split()
    except (IndexError, ValueError):
        await msg.reply(f'⚠️ 输入格式错误\n\n`{msg.text}`\n **会话已结束！**')
    else:
        send = await msg.reply(
            f'🆗 会话结束，收到设置\n\n用户名：**{emby_name}**  安全码：**{emby_pwd2}** \n\n__正在为您排队并初始化账户，更新策略__......')
        
        async with _create_user_lock:
            # 再次检查限制（双重检查），避免排队后超发
            if config.open.tem >= config.open.all_user:
                return await editMessage(send, f'**🚫 很抱歉，注册总数({config.open.tem})已达限制({config.open.all_user})。**',
                                         re_create_ikb)

            # emby api操作
            data = await emby.emby_create(name=emby_name, days=us)
        if not data:
            if is_queued:
                try:
                    await send.delete()
                except:
                    pass
                await bot.send_message(call.from_user.id, '**- ❎ 已有此账户名，请重新输入注册\n- ❎ 或检查有无特殊字符\n- ❎ 或emby服务器连接不通，会话已结束！**', reply_markup=re_create_ikb)
            else:
                await editMessage(send,
                                  '**- ❎ 已有此账户名，请重新输入注册\n- ❎ 或检查有无特殊字符\n- ❎ 或emby服务器连接不通，会话已结束！**',
                                  re_create_ikb)
            LOGGER.error("【创建账户】：重复账户 or 未知错误！")
        else:
            # 创建成功后立即更新计数器
            tg = call.from_user.id
            pwd = data[1]
            eid = data[0]
            ex = data[2]
            
            # 数据库操作
            if stats:
                await sql_update_emby(Emby.tg == tg, embyid=eid, name=emby_name, pwd=pwd, pwd2=emby_pwd2, lv='b', cr=datetime.now(), ex=ex) 
            else:
                await sql_update_emby(Emby.tg == tg, embyid=eid, name=emby_name, pwd=pwd, pwd2=emby_pwd2, lv='b', cr=datetime.now(), ex=ex, us=0)
            
            # 更新计数器
            tem_adduser()
            
            if config.schedall.check_ex:
                ex = ex.strftime("%Y-%m-%d %H:%M:%S")
            elif config.schedall.low_activity:
                ex = f'__若{config.activity_check_days}天无观看将封禁__'
            else:
                ex = '__无需保号，放心食用__'
                
            emby_line_variable = config.emby_line.format(name=emby_name, pwd=pwd)
            success_msg = (f'**▎创建用户成功🎉**\n\n'
                           f'· 用户名称 | `{emby_name}`\n'
                           f'· 用户密码 | `{pwd}`\n'
                           f'· 安全密码 | `{emby_pwd2}`（仅发送一次）\n'
                           f'· 到期时间 | `{ex}`\n'
                           f'· 当前线路：\n'
                           f'{emby_line_variable}\n\n'
                           f'**·【服务器】 - 查看线路和密码**')
            
            if is_queued:
                try:
                    await send.delete()
                except:
                    pass
                await bot.send_message(call.from_user.id, success_msg)
            else:
                await editMessage(send, success_msg)
            
            LOGGER.info(f"【创建账户】[开注状态]：{call.from_user.id} - 建立了 {emby_name} ") if stats else LOGGER.info(
                f"【创建账户】：{call.from_user.id} - 建立了 {emby_name} ")


from bot.func_helper.utils import debounce

# 键盘中转
@bot.on_callback_query(filters.regex('members'))
@debounce(wait=1)
async def members(_, call):
    data = await members_info(tg=call.from_user.id)
    if not data:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    await callAnswer(call, f"✅ 用户界面")
    name, lv, ex, us, embyid, pwd2 = data
    text = f"▎__欢迎进入用户面板！{call.from_user.first_name}__\n\n" \
           f"**· 🆔 用户のID** | `{call.from_user.id}`\n" \
           f"**· 📊 当前状态** | {lv}\n" \
           f"**· 🍒 积分{config.money}** | {us}\n" \
           f"**· 💠 账号名称** | [{name}](tg://user?id={call.from_user.id})\n" \
           f"**· 🚨 到期时间** | {ex}"
    if not embyid:
        is_admin = judge_admins(call.from_user.id)
        await editMessage(call, text, members_ikb(is_admin, False))
    else:
        await editMessage(call, text, members_ikb(account=True))


# 创建账户
@bot.on_callback_query(filters.regex('create') & user_in_group_on_filter)
@debounce(wait=2)
async def create(_, call, passed_captcha=False):
    """

    当队列已满时，用户会收到等待提示。
    信号量和计数器正确释放。
    代码保存至收藏夹，改版时勿忘加入排队机制
    :param _:
    :param call:
    :return:
    """
    e = await sql_get_emby(tg=call.from_user.id)
    if not e:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)

    if e.embyid:
        await callAnswer(call, '💦 你已经有账户啦！请勿重复注册。', True)
    elif not config.open.stat and int(e.us) <= 0:
        await callAnswer(call, f'🤖 自助注册已关闭，等待开启或使用注册码注册。', True)
    elif not config.open.stat and int(e.us) > 0:
        if not passed_captcha:
            from bot.func_helper.captcha import generate_math_captcha, check_active_captcha
            if check_active_captcha(call.from_user.id):
                await callAnswer(call, "⚠️ 您有未完成的验证码，请在聊天记录中查看并完成它（如找不到请等待1分钟重试）。", True)
                return
            await callAnswer(call, "正在生成验证码...", False)
            question, keyboard = generate_math_captcha(call.from_user.id, "create", {"us": e.us, "stats": False})
            try:
                sent_msg = await bot.send_message(call.from_user.id, f"🤖 **防机器人验证**\n请计算以下算式并选择正确答案以继续：\n\n**{question}**", reply_markup=keyboard)
                from bot.func_helper.captcha import clear_captcha_later
                import asyncio
                asyncio.create_task(clear_captcha_later(call.from_user.id, sent_msg))
            except Exception:
                pass
            return

        send = await callAnswer(call, f'🪙 资质核验成功，处理排队中...', True)
        if send is False:
            return
        else:
            from bot.func_helper.registration_queue import registration_queue
            await registration_queue.put((call.from_user.id, e.us, False, call))
            await editMessage(call, '✅ **您的注册请求已受理！**\n\n系统正按队列满跑生成您的账号，请耐心等待。\n生成成功后机器人将**私聊**为您发送账号及密码信息。')
    elif config.open.stat:
        if not passed_captcha:
            from bot.func_helper.captcha import generate_math_captcha, check_active_captcha
            if check_active_captcha(call.from_user.id):
                await callAnswer(call, "⚠️ 您有未完成的验证码，请在聊天记录中查看并完成它（如找不到请等待1分钟重试）。", True)
                return
            await callAnswer(call, "正在生成验证码...", False)
            question, keyboard = generate_math_captcha(call.from_user.id, "create", {"us": config.open.open_us, "stats": True})
            try:
                sent_msg = await bot.send_message(call.from_user.id, f"🤖 **防机器人验证**\n请计算以下算式并选择正确答案以继续：\n\n**{question}**", reply_markup=keyboard)
                from bot.func_helper.captcha import clear_captcha_later
                import asyncio
                asyncio.create_task(clear_captcha_later(call.from_user.id, sent_msg))
            except Exception:
                pass
            return

        send = await callAnswer(call, f"🪙 开放注册队列生成中，请耐心等待通知。", True)
        if send is False:
            return
        else:
            from bot.func_helper.registration_queue import registration_queue
            await registration_queue.put((call.from_user.id, config.open.open_us, True, call))
            await editMessage(call, '✅ **您的注册请求已受理并排队！**\n\n当前人数较多，系统正按队列生成账号，请耐心等待。\n生成成功后机器人将**私聊**为您发送账号及密码信息。')


# 换绑tg
@bot.on_callback_query(filters.regex('changetg') & user_in_group_on_filter)
async def change_tg(_, call):
    try:
        status, current_id_str, replace_id_str = call.data.split('_')
        if not judge_admins(call.from_user.id): return await callAnswer(call, '⚠️ 你什么档次？', True)
        current_id = int(current_id_str)
        replace_id = int(replace_id_str)
        if status == 'nochangetg':
            return await asyncio.gather(
                editMessage(call,
                            f' ❎ 好的，[您](tg://user?id={call.from_user.id})已拒绝[{current_id}](tg://user?id={current_id})的换绑请求，原TG：`{replace_id}`。'),
                bot.send_message(current_id, '❌ 您的换绑请求已被拒。请在群组中详细说明情况。'))

        await editMessage(call,
                          f' ✅ 好的，[您](tg://user?id={call.from_user.id})已通过[{current_id}](tg://user?id={current_id})的换绑请求，原TG：`{replace_id}`。')
        e = await sql_get_emby(tg=replace_id)
        if not e or not e.embyid: return await bot.send_message(current_id, '⁉️ 出错了，您所换绑账户已不存在。')
        
        # 清空原账号信息但保留tg
        if await sql_update_emby(Emby.tg == replace_id, embyid=None, name=None, pwd=None, pwd2=None, 
                          lv='d', cr=None, ex=None, us=0, iv=0, ch=None):
            LOGGER.info(f'【TG改绑】清空原账户 id{e.tg} 成功')
        else:
            await bot.send_message(current_id, "🍰 **⭕#TG改绑 原账户清空错误，请联系闺蜜（管理）！**")
            LOGGER.error(f"【TG改绑】清空原账户 id{e.tg} 失败, Emby:{e.name}未转移...")
            return

        # 将原账号的币值转移到新账号
        old_iv = e.iv
        if await sql_update_emby(Emby.tg == current_id, embyid=e.embyid, name=e.name, pwd=e.pwd, pwd2=e.pwd2,
                           lv=e.lv, cr=e.cr, ex=e.ex, iv=old_iv):
            text = f'⭕ 请接收您的信息！\n\n' \
                   f'· 用户名称 | `{e.name}`\n' \
                   f'· 用户密码 | `{e.pwd}`\n' \
                   f'· 安全密码 | `{e.pwd2}`（仅发送一次）\n' \
                   f'· 到期时间 | `{e.ex}`\n\n' \
                   f'· 当前线路：\n{config.emby_line}\n\n' \
                   f'**·在【服务器】按钮 - 查看线路和密码**'
            await bot.send_message(current_id, text)
            LOGGER.info(
                f'【TG改绑】 emby账户 {e.name} 绑定至 {current_id}')
        else:
            await bot.send_message(current_id, '🍰 **【TG改绑】数据库处理出错，请联系闺蜜（管理）！**')
            LOGGER.error(f"【TG改绑】 emby账户{e.name} 绑定未知错误。")
        return
    except (IndexError, ValueError):
        pass
    d = await sql_get_emby(tg=call.from_user.id)
    if not d:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    if d.embyid:
        return await callAnswer(call, '⚖️ 您已经拥有账户，请不要钻空子', True)

    await callAnswer(call, '⚖️ 更换绑定的TG')
    send = await editMessage(call,
                             '🔰 **【更换绑定emby的tg】**\n'
                             '须知：\n'
                             '- **请确保您之前用其他tg账户注册过**\n'
                             '- **请确保您注册的其他tg账户呈已注销状态**\n'
                             '- **请确保输入正确的emby用户名，安全码/密码**\n\n'
                             '您有120s回复 `[emby用户名] [安全码/密码]`\n例如 `苏苏 5210` ，若密码为空则填写"None"，退出点 /cancel')
    if send is False:
        return

    m = await callListen(call, 120, buttons=back_members_ikb)
    if m is False:
        return

    elif m.text == '/cancel':
        await m.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', back_members_ikb)
    else:
        try:
            await m.delete()
            emby_name, emby_pwd = m.text.split()
        except (IndexError, ValueError):
            return await editMessage(call, f'⚠️ 输入格式错误\n【`{m.text}`】\n **会话已结束！**', re_changetg_ikb)

        pwd = '空（直接回车）', 5210 if emby_pwd == 'None' else emby_pwd, emby_pwd
        e = await sql_get_emby(tg=emby_name)
        if e is None:
            # 在emby2中，验证安全码 或者密码
            e2 = await sql_get_emby2(name=emby_name)
            if e2 is None:
                return await editMessage(call, f'❓ 未查询到bot数据中名为 {emby_name} 的账户，请使用 **绑定TG** 功能。',
                                         buttons=re_bindtg_ikb)
            if emby_pwd != e2.pwd2:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'💢 安全码or密码验证错误，请检查输入\n{emby_name} {emby_pwd} 是否正确。',
                                             buttons=re_changetg_ikb)
                await sql_update_emby(Emby.tg == call.from_user.id, embyid=embyid, name=e2.name, pwd=emby_pwd,
                                pwd2=e2.pwd2, lv=e2.lv, cr=e2.cr, ex=e2.ex)
                await sql_delete_emby2(embyid=e2.embyid)
                text = f'⭕ 账户 {emby_name} 的密码验证成功！\n\n' \
                       f'· 用户名称 | `{emby_name}`\n' \
                       f'· 用户密码 | `{pwd[0]}`\n' \
                       f'· 安全密码 | `{e2.pwd2}`（仅发送一次）\n' \
                       f'· 到期时间 | `{e2.ex}`\n\n' \
                       f'· 当前线路：\n{config.emby_line}\n\n' \
                       f'**·在【服务器】按钮 - 查看线路和密码**'
                await sendMessage(call,
                                  f'⭕#TG改绑 原emby账户 #{emby_name}\n\n'
                                  f'从emby2表绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                  send=True)
                LOGGER.info(f'【TG改绑】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
                await editMessage(call, text)

            elif emby_pwd == e2.pwd2:
                text = f'⭕ 账户 {emby_name} 的安全码验证成功！\n\n' \
                       f'· 用户名称 | `{emby_name}`\n' \
                       f'· 用户密码 | `{e2.pwd}`\n' \
                       f'· 安全密码 | `{pwd[1]}`（仅发送一次）\n' \
                       f'· 到期时间 | `{e2.ex}`\n\n' \
                       f'· 当前线路：\n{config.emby_line}\n\n' \
                       f'**·在【服务器】按钮 - 查看线路和密码**'
                await sql_update_emby(Emby.tg == call.from_user.id, embyid=e2.embyid, name=e2.name, pwd=e2.pwd,
                                pwd2=emby_pwd, lv=e2.lv, cr=e2.cr, ex=e2.ex)
                await sql_delete_emby2(embyid=e2.embyid)
                await sendMessage(call,
                                  f'⭕#TG改绑 原emby账户 #{emby_name}\n\n'
                                  f'从emby2表绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                  send=True)
                LOGGER.info(f'【TG改绑】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
                await editMessage(call, text)

        else:
            if call.from_user.id == e.tg: return await editMessage(call, '⚠️ 您已经拥有账户。')
            if emby_pwd != e.pwd2:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'💢 安全码or密码验证错误，请检查输入\n{emby_name} {emby_pwd} 是否正确。',
                                             buttons=re_changetg_ikb)
            await  asyncio.gather(editMessage(call,
                                              f'✔️ 会话结束，验证成功\n\n'
                                              f'🔰 用户名：**{emby_name}** 输入码：**{emby_pwd}**......\n\n'
                                              f'🎯 已向授权群发送申请，请联系并等待管理员确认......'),
                                  sendMessage(call,
                                              f'⭕#TG改绑\n'
                                              f'**用户 [{call.from_user.id}](tg://user?id={call.from_user.id}) 正在试图改绑Emby: [{e.name}](tg://user?id={e.tg})，原TG: `{e.tg}`，已通过安全/密码核验\n\n'
                                              f'请管理员审核决定：**',
                                              buttons=send_changetg_ikb(call.from_user.id, e.tg),
                                              send=True))
            LOGGER.info(
                f'【TG改绑】 {call.from_user.first_name}-{call.from_user.id} 通过验证账户，已递交对Emby: {emby_name}, Tg:{e.tg} 的换绑申请')


@bot.on_callback_query(filters.regex('bindtg') & user_in_group_on_filter)
@debounce(wait=2)
async def bind_tg(_, call):
    if not getattr(config.open, "bindtg", False):
        await call.answer("⚠️ 绑定TG功能已关闭", show_alert=True)
        return
    d = await sql_get_emby(tg=call.from_user.id)
    if d.embyid is not None:
        return await callAnswer(call, '⚖️ 您已经拥有账户，请不要钻空子', True)
    await callAnswer(call, '⚖️ 将账户绑定TG')
    send = await editMessage(call,
                             '🔰 **【已有emby绑定至tg】**\n'
                             '须知：\n'
                             '- **请确保您需绑定的账户不在bot中**\n'
                             '- **请确保您不是恶意绑定他人的账户**\n'
                             '- **请确保输入正确的emby用户名，密码**\n\n'
                             '您有120s回复 `[emby用户名] [密码]`\n例如 `苏苏 5210` ，若密码为空则填写“None”，退出点 /cancel')
    if send is False:
        return

    m = await callListen(call, 120, buttons=back_members_ikb)
    if m is False:
        return

    elif m.text == '/cancel':
        await m.delete()
        await editMessage(call, '__您已经取消输入__ **会话已结束！**', back_members_ikb)
    else:
        try:
            await m.delete()
            emby_name, emby_pwd = m.text.split()
        except (IndexError, ValueError):
            return await editMessage(call, f'⚠️ 输入格式错误\n【`{m.text}`】\n **会话已结束！**', re_bindtg_ikb)
        await editMessage(call,
                          f'✔️ 会话结束，收到设置\n\n用户名：**{emby_name}** 正在检查密码 **{emby_pwd}**......')
        e = await sql_get_emby(tg=emby_name)
        if e is None:
            e2 = await sql_get_emby2(name=emby_name)
            if e2 is None:
                success, embyid = await emby.authority_account(tg_id=call.from_user.id, username=emby_name, password=emby_pwd)
                if not success:
                    return await editMessage(call,
                                             f'🍥 很遗憾绑定失败，您输入的账户密码不符（{emby_name} - {emby_pwd}），请仔细确认后再次尝试',
                                             buttons=re_bindtg_ikb)
                else:
                    security_pwd = await pwd_create(4)
                    pwd = ['空（直接回车）', security_pwd] if emby_pwd == 'None' else [emby_pwd, emby_pwd]
                    ex = (datetime.now() + timedelta(days=30))
                    text = f'✅ 账户 {emby_name} 成功绑定\n\n' \
                           f'· 用户名称 | `{emby_name}`\n' \
                           f'· 用户密码 | `{pwd[0]}`\n' \
                           f'· 安全密码 | `{pwd[1]}`（仅发送一次）\n' \
                           f'· 到期时间 | `{ex}`\n\n' \
                           f'· 当前线路：\n{config.emby_line}\n\n' \
                           f'· **在【服务器】按钮 - 查看线路和密码**'
                    await sql_update_emby(Emby.tg == call.from_user.id, embyid=embyid, name=emby_name, pwd=pwd[0],
                                    pwd2=pwd[1], lv='b', cr=datetime.now(), ex=ex)
                    await editMessage(call, text)
                    await sendMessage(call,
                                      f'⭕#新TG绑定 原emby账户 #{emby_name} \n\n已绑定至 [{call.from_user.first_name}](tg://user?id={call.from_user.id}) - {call.from_user.id}',
                                      send=True)
                    LOGGER.info(
                        f'【新TG绑定】 emby账户 {emby_name} 绑定至 {call.from_user.first_name}-{call.from_user.id}')
            else:
                await editMessage(call, '🔍 数据库已有此账户，不可绑定，请使用 **换绑TG**', buttons=re_changetg_ikb)
        else:
            await editMessage(call, '🔍 数据库已有此账户，不可绑定，请使用 **换绑TG**', buttons=re_changetg_ikb)


# kill yourself
@bot.on_callback_query(filters.regex('delme'))
async def del_me(_, call):
    e = await sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    else:
        if e.embyid is None:
            return await callAnswer(call, '未查询到账户，不许乱点！💢', True)
        await callAnswer(call, "🔴 请先进行 安全码 验证")
        edt = await editMessage(call, '**🔰账户安全验证**：\n\n👮🏻验证是否本人进行敏感操作，请对我发送您设置的安全码。倒计时 120s\n'
                                      '🛑 **停止请点 /cancel**')
        if edt is False:
            return

        m = await callListen(call, 120)
        if m is False:
            return

        elif m.text == '/cancel':
            await m.delete()
            await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        else:
            if m.text == e.pwd2:
                await m.delete()
                await editMessage(call, '**⚠️ 如果您的账户到期，我们将封存您的账户，但仍保留数据'
                                        '而如果您选择删除，这意味着服务器会将您此前的活动数据全部删除。\n**',
                                  buttons=del_me_ikb(e.embyid))
            else:
                await m.delete()
                await editMessage(call, '**💢 验证不通过，安全码错误。**', re_delme_ikb)


@bot.on_callback_query(filters.regex('delemby'))
async def del_emby(_, call):
    send = await callAnswer(call, "🎯 get，正在删除ing。。。")
    if send is False:
        return

    embyid = call.data.split('-')[1]
    if await emby.emby_del(emby_id=embyid):
        await sql_update_emby(Emby.embyid == embyid, embyid=None, name=None, pwd=None, pwd2=None, lv='d', cr=None, ex=None)
        tem_deluser()
        send1 = await editMessage(call, '🗑️ 好了，已经为您删除...\n愿来日各自安好，山高水长，我们有缘再见！',
                                  buttons=back_members_ikb)
        if send1 is False:
            return

        LOGGER.info(f"【删除账号】：{call.from_user.id} 已删除！")
    else:
        await editMessage(call, '🥧 蛋糕辣~ 好像哪里出问题了，请向管理反应', buttons=back_members_ikb)
        LOGGER.error(f"【删除账号】：{call.from_user.id} 失败！")


# 重置密码为空密码
@bot.on_callback_query(filters.regex('reset'))
async def reset(_, call):
    e = await sql_get_emby(tg=call.from_user.id)
    if e is None:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    if e.embyid is None:
        return await bot.answer_callback_query(call.id, '未查询到账户，不许乱点！💢', show_alert=True)
    else:
        await callAnswer(call, "🔴 请先进行 安全码 验证")
        send = await editMessage(call, '**🔰账户安全验证**：\n\n 👮🏻验证是否本人进行敏感操作，请对我发送您设置的安全码。倒计时 120 s\n'
                                       '🛑 **停止请点 /cancel**')
        if send is False:
            return

        m = await callListen(call, 120, buttons=back_members_ikb)
        if m is False:
            return

        elif m.text == '/cancel':
            await m.delete()
            await editMessage(call, '__您已经取消输入__ **会话已结束！**', buttons=back_members_ikb)
        else:
            if m.text != e.pwd2:
                await m.delete()
                await editMessage(call, f'**💢 验证不通过，{m.text} 安全码错误。**', buttons=re_reset_ikb)
            else:
                await m.delete()
                await editMessage(call, '🎯 请在 120s内 输入你要更新的密码,不限制中英文，emoji。特殊字符部分支持，其他概不负责。\n\n'
                                        '点击 /cancel 将重置为空密码并退出。 无更改退出状态请等待120s')
                mima = await callListen(call, 120, buttons=back_members_ikb)
                if mima is False:
                    return

                elif mima.text == '/cancel':
                    await mima.delete()
                    await editMessage(call, '**🎯 收到，正在重置ing。。。**')
                    if await emby.emby_reset(emby_id=e.embyid) is True:
                        await editMessage(call, '🕶️ 操作完成！已为您重置密码为 空。', buttons=back_members_ikb)
                        LOGGER.info(f"【重置密码】：{call.from_user.id} 成功重置了空密码！")
                    else:
                        await editMessage(call, '🫥 重置密码操作失败！请联系管理员。')
                        LOGGER.error(f"【重置密码】：{call.from_user.id} 重置密码失败 ！")

                else:
                    await mima.delete()
                    await editMessage(call, '**🎯 收到，正在重置ing。。。**')
                    if await emby.emby_reset(emby_id=e.embyid, new_password=mima.text) is True:
                        await editMessage(call, f'🕶️ 操作完成！已为您重置密码为 `{mima.text}`。',
                                          buttons=back_members_ikb)
                        LOGGER.info(f"【重置密码】：{call.from_user.id} 成功重置了密码为 {mima.text} ！")
                    else:
                        await editMessage(call, '🫥 操作失败！请联系管理员。', buttons=back_members_ikb)
                        LOGGER.error(f"【重置密码】：{call.from_user.id} 重置密码失败 ！")


# 显示/隐藏某些库
@bot.on_callback_query(filters.regex('embyblock'))
async def embyblocks(_, call):
    data = await sql_get_emby(tg=call.from_user.id)
    if not data:
        return await callAnswer(call, '⚠️ 数据库没有你，请重新 /start录入', True)
    if data.embyid is None:
        return await callAnswer(call, '❓ 未查询到账户，不许乱点!', True)
    elif data.lv == "c":
        return await callAnswer(call, '💢 账户到期，封禁中无法使用！', True)
    elif len(config.emby_block) == 0:
        send = await editMessage(call, '⭕ 管理员未设置。。。 快催催\no(*////▽////*)q', buttons=back_members_ikb)
        if send is False:
            return
    else:
        success, rep = await emby.user(emby_id=data.embyid)
        try:
            if success is False:
                stat = '💨 未知'
            else:
                # 新版本使用 EnabledFolders 和 EnableAllFolders 控制访问
                policy = rep.get("Policy", {})
                enable_all_folders = policy.get("EnableAllFolders")
                enabled_folders = policy.get("EnabledFolders", [])
                
                if enable_all_folders:
                    # 如果启用所有文件夹，检查是否有特定的阻止设置
                    stat = '🟢 显示'
                else:
                    # 检查目标媒体库是否在启用列表中
                    # 需要获取媒体库ID来进行比较
                    target_folder_ids = await emby.get_folder_ids_by_names(config.emby_block)
                    if target_folder_ids and any(folder_id in enabled_folders for folder_id in target_folder_ids):
                        stat = '🟢 显示'
                    else:
                        stat = '🔴 隐藏'
        except KeyError:
            stat = '💨 未知'
        block = ", ".join(config.emby_block)
        await asyncio.gather(callAnswer(call, "✅ 到位"),
                             editMessage(call,
                                         f'🤺 用户状态：{stat}\n🎬 目前设定的库为: \n\n**{block}**\n\n请选择你的操作。',
                                         buttons=emby_block_ikb(data.embyid)))


# 隐藏
@bot.on_callback_query(filters.regex('emby_block'))
async def user_emby_block(_, call):
    embyid = call.data.split('-')[1]
    send = await callAnswer(call, f'🎬 正在为您关闭显示ing')
    if send is False:
        return
    success, rep = await emby.user(emby_id=embyid)
    if success:
        try:
            # 使用封装的隐藏媒体库方法
            re = await emby.hide_folders_by_names(embyid, config.emby_block)
            if re is True:
                send1 = await editMessage(call, f'🕶️ ο(=•ω＜=)ρ⌒☆\n 小尾巴隐藏好了！ ', buttons=user_emby_block_ikb)
                if send1 is False:
                    return
            else:
                await editMessage(call, f'🕶️ Error!\n 隐藏失败，请上报管理检查)', buttons=back_members_ikb)
        except Exception as e:
            LOGGER.error(f"隐藏媒体库失败: {str(e)}")
            await editMessage(call, f'🕶️ Error!\n 隐藏失败，请上报管理检查)', buttons=back_members_ikb)


# 显示
@bot.on_callback_query(filters.regex('emby_unblock'))
async def user_emby_unblock(_, call):
    embyid = call.data.split('-')[1]
    send = await callAnswer(call, f'🎬 正在为您开启显示ing')
    if send is False:
        return
    success, rep = await emby.user(emby_id=embyid)
    if success:
        try:
            # 使用封装的显示媒体库方法
            re = await emby.show_folders_by_names(embyid, config.emby_block)
            if re is True:
                send1 = await editMessage(call, f'🕶️ ο(=•ω＜=)ρ⌒☆\n 小尾巴显示好了！ ', buttons=user_emby_unblock_ikb)
                if send1 is False:
                    return
            else:
                await editMessage(call, f'🕶️ Error!\n 显示失败，请上报管理检查设置', buttons=back_members_ikb)
        except Exception as e:
            LOGGER.error(f"显示媒体库失败: {str(e)}")
            await editMessage(call, f'🕶️ Error!\n 显示失败，请上报管理检查设置', buttons=back_members_ikb)


@bot.on_callback_query(filters.regex('exchange') & user_in_group_on_filter)
@debounce(wait=2)
async def call_exchange(_, call):
    await asyncio.gather(callAnswer(call, '🔋 使用注册/续期码'), deleteMessage(call))
    msg = await ask_return(call, text='🔋 **【使用注册/续期码】**：\n\n'
                                      f'- 请在120s内对我发送你的注册/续期码，形如\n`{config.ranks.logo}-xx-xxxx`\n退出点 /cancel',
                           button=re_exchange_b_ikb)
    if not msg:
        return
    elif msg.text == '/cancel':
        await asyncio.gather(msg.delete(), p_start(_, msg))
    else:
        await rgs_code(_, msg, register_code=msg.text)


@bot.on_callback_query(filters.regex('storeall'))
@debounce(wait=1)
async def do_store(_, call):
    await asyncio.gather(callAnswer(call, '✔️ 欢迎进入兑换商店'),
                         editMessage(call,
                                     f'**🏪 请选择想要使用的服务：**\n\n🤖 自动{config.money}续期状态：{config.open.exchange} {config.open.exchange_cost}/月',
                                     buttons=store_ikb()))


@bot.on_callback_query(filters.regex('store-reborn'))
@debounce(wait=2)
async def do_store_reborn(_, call):
    e = await sql_get_emby(tg=call.from_user.id)
    if not e:
        return
    if not e.embyid or not e.name:
        return await callAnswer(call, '❌ 未查询到账户，不许乱点！', True)
    await callAnswer(call,
                     '✔️ 请仔细阅读：\n\n本功能仅为 因未活跃而被封禁的用户解封使用，到期状态下封禁的账户请勿使用，以免浪费积分。',
                     True)
    if all([e.lv == 'c', e.iv >= config.open.exchange_cost, config.schedall.low_activity]):
        await editMessage(call,
                          f'🏪 您已满足基础要求，此次将花费 {config.open.exchange_cost}{config.money} 解除未活跃的封禁，确认请回复 /ok，退出 /cancel')
        m = await callListen(call, 120, buttons=re_born_ikb)
        if m is False:
            return

        elif m.text == '/cancel':
            await asyncio.gather(m.delete(), do_store(_, call))
        else:
            await sql_update_emby(Emby.tg == call.from_user.id, iv=e.iv - config.open.exchange_cost, lv='b')
            await emby.emby_change_policy(emby_id=e.embyid)
            LOGGER.info(f'【兑换解封】- {call.from_user.id} 已花费 {config.open.exchange_cost}{config.money},解除封禁')
            await asyncio.gather(m.delete(), do_store(_, call),
                                 sendMessage(call, '解封成功<(￣︶￣)↗[GO!]\n此消息将在20s后自焚', timer=20))
    else:
        await sendMessage(call, '❌ 不满足以下要求！ヘ(￣ω￣ヘ)\n\n'
                                '1. 被封禁账户\n'
                                f'2. 至少持有 {config.open.exchange_cost}{config.money}\n'
                                f'3. 【定时策略】活跃检测开启\n'
                                f'此消息将在20s后自焚', timer=20)


@bot.on_callback_query(filters.regex('store-whitelist'))
@debounce(wait=2)
async def do_store_whitelist(_, call):
    if config.open.whitelist:
        e = await sql_get_emby(tg=call.from_user.id)
        if e is None:
            return
        if not e.embyid or not e.name:
            return await callAnswer(call, '❌ 未查询到账户，不许乱点！', True)
        if e.iv < config.open.whitelist_cost or e.lv == 'a':
            return await callAnswer(call,
                                    f'🏪 兑换规则：\n当前兑换白名单需要 {config.open.whitelist_cost} {config.money}，已有白名单无法再次消费。勉励',
                                    True)
        await callAnswer(call, f'🏪 您已满足 {config.open.whitelist_cost} {config.money}要求', True)
        await sql_update_emby(Emby.tg == call.from_user.id, lv='a', iv=e.iv - config.open.whitelist_cost)
        send = await call.message.edit(f'**{random.choice(Yulv.load_yulv().wh_msg)}**\n\n'
                                       f'🎉 恭喜[{call.from_user.first_name}](tg://user?id={call.from_user.id}) 今日晋升，{config.ranks["logo"]}白名单')
        await send.forward(config.group[0])
        LOGGER.info(f'【兑换白名单】- {call.from_user.id} 已花费 9999{config.money}，晋升白名单')
    else:
        await callAnswer(call, '❌ 管理员未开启此兑换', True)


@bot.on_callback_query(filters.regex('store-invite'))
@debounce(wait=2)
async def do_store_invite(_, call):
    if config.open.invite:
        e = await sql_get_emby(tg=call.from_user.id)
        if not e:
            return
        # 用户等级为 a（白名单） b(普通用户) c(已禁用) d（未注册用户）
        # 比如当 _open.invite_lv 设置为 d 时，用户等级为 小于等于d 的用户可以兑换，否则无法兑换
        if e.lv > config.open.invite_lv:
            return await callAnswer(call, '❌ 账号等级不足，无法兑换', True)
        if e.iv < config.open.invite_cost:
            return await callAnswer(call,
                                    f'🏪 兑换规则：\n当前兑换注册码至少需要 {config.open.invite_cost} {config.money}。你的账户只有 {e.iv} {config.money}，勉励',
                                    True)
        await editMessage(call,
                          f'🎟️ 请回复创建 [类型] [数量] [模式]\n\n'
                          f'**类型**：月mon，季sea，半年half，年year\n'
                          f'**模式**： link -深链接 | code -码\n'
                          # f'**续期**： F - 注册码，T - 续期码\n'
                          f'**示例**：`mon 1 link` 记作 1条 月度注册链接 \n'
                          f'**示例**：`sea 1 code` 记作 1条 季度注册码\n'
                          f'**注意**：兑率 30天 = {config.open.invite_cost}{config.money}\n'
                          f'__取消本次操作，请 /cancel__')
        content = await callListen(call, 120)
        if content is False:
            return await do_store(_, call)

        elif content.text == '/cancel':
            return await asyncio.gather(content.delete(), do_store(_, call))
        try:
            times, count, method = content.text.split()
            days = getattr(ExDate(), times)
            count = int(count)
            cost = math.floor((days * count / 30) * config.open.invite_cost)
            if e.iv < cost:
                return await asyncio.gather(content.delete(),
                                            sendMessage(call,
                                                        f'您只有 {e.iv}{config.money}，而您需要花费 {cost}，超前消费是不可取的哦！？',
                                                        timer=10),
                                            do_store(_, call))
            method = getattr(ExDate(), method)
        except (AttributeError, ValueError, IndexError):
            return await asyncio.gather(sendMessage(call, f'⚠️ 检查输入，格式似乎有误\n{content.text}', timer=10),
                                        do_store(_, call),
                                        content.delete())
        else:
            await sql_update_emby(Emby.tg == call.from_user.id, iv=e.iv - cost)
            links = await cr_link_one(call.from_user.id, days, count, days, method)
            if links is None:
                return await editMessage(call, '⚠️ 数据库插入失败，请检查数据库')
            links = f"🎯 {config.bot_name}已为您生成了 **{days}天** 注册码 {count} 个\n\n" + links
            chunks = [links[i:i + 4096] for i in range(0, len(links), 4096)]
            for chunk in chunks:
                await sendMessage(content, chunk)
            LOGGER.info(f"【注册码兑换】：{config.bot_name}已为 {content.from_user.id} 兑换了 {count} 个 {days} 天注册码")
    else:
        await callAnswer(call, '❌ 管理员未开启此兑换', True)


@bot.on_callback_query(filters.regex('store-query'))
async def do_store_query(_, call):
    try:
        number = int(call.data.split(':')[1])
    except (IndexError, KeyError, ValueError):
        number = 1
    a, b = await sql_count_c_code(tg_id=call.from_user.id, page=number)
    if not a:
        return await callAnswer(call, '❌ 空', True)
    await callAnswer(call, '📜 正在翻页')
    await editMessage(call, text=a, buttons=await store_query_page(b, number))
@bot.on_callback_query(filters.regex('^my_favorites|^page_my_favorites:'))
async def my_favorite(_, call):
    # 获取页码
    if call.data == 'my_favorites':
        page = 1
        await callAnswer(call, '🔍 我的收藏')
    else:
        page = int(call.data.split(':')[1])
        await callAnswer(call, f'🔍 打开第{page}页')
    get_emby = await sql_get_emby(tg=call.from_user.id)
    if get_emby is None:
        return await callAnswer(call, '您还没有Emby账户', True)
    limit = 10
    start_index = (page - 1) * limit
    favorites = await emby.get_favorite_items(emby_id=get_emby.embyid, start_index=start_index, limit=limit)
    text = "**我的收藏**\n\n"
    for item in favorites.get("Items", []):
        item_id = item.get("Id")
        if not item_id:
            continue
        # 获取项目名称
        item_name = item.get("Name", "")
        item_type = item.get('Type', '未知')
        if item_type == 'Movie':
            item_type = '电影'
        elif item_type == 'Series':
            item_type = '剧集'
        elif item_type == 'Episode':
            item_type = '剧集'
        elif item_type == 'Person':
            item_type = '演员'
        elif item_type == 'Photo':
            item_type = '图片'
        text += f"{item_type}：{item_name}\n"

    total_favorites = favorites.get("TotalRecordCount", 0)
    total_pages = math.ceil(total_favorites / limit)
    keyboard = await favorites_page_ikb(total_pages, page)
    await editMessage(call, text, buttons=keyboard)
@bot.on_callback_query(filters.regex('my_devices'))
async def my_devices(_, call):
    get_emby = await sql_get_emby(tg=call.from_user.id)
    if get_emby is None:
        return await callAnswer(call, '您还没有Emby账户', True)
    success, result = await emby.get_emby_userip(emby_id=get_emby.embyid)
    if not success or len(result) == 0:
        return await callAnswer(call, '您好像没播放信息吖')
    else:
        await callAnswer(call, '🔍 正在获取您的设备信息')
        device_count = 0
        ip_count = 0
        device_list = []
        ip_list = []
        device_details = ""
        ip_details = ""
        for r in result:
            device, client, ip = r
            # 统计ip
            if ip not in ip_list:
                ip_count += 1
                ip_list.append(ip)
                ip_details += f'{ip_count}: `{ip}`\n'
            # 统计设备并拼接详情
            if device + client not in device_list:
                device_count += 1
                device_list.append(device + client)
                device_details += f'{device_count}: {device} | {client}  \n'
        text = '**🌏 以下为您播放过的设备&ip 共{}个设备，{}个ip：**\n\n'.format(device_count, ip_count) + '**设备:**\n' + device_details + '**IP:**\n'+ ip_details

        # 以\n分割文本，每20条发送一个消息
        messages = text.split('\n')
        # 每20条消息组成一组
        for i in range(0, len(messages), 20):
            chunk = messages[i:i+20]
            chunk_text = '\n'.join(chunk)
            if not chunk_text.strip():
                continue
            await sendMessage(call.message, chunk_text, buttons=close_it_ikb)
