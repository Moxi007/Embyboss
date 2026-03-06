import asyncio
import random
from datetime import datetime, timezone, timedelta

from pyrogram import filters

from bot import bot, config
from bot.func_helper.filters import user_in_group_on_filter
from bot.func_helper.msg_utils import callAnswer, sendMessage, deleteMessage
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby


from bot.func_helper.utils import debounce, dedup

@bot.on_callback_query(filters.regex('checkin') & user_in_group_on_filter)
@debounce(wait=2)
@dedup()
async def user_in_checkin(_, call):
    now = datetime.now(timezone(timedelta(hours=8)))
    today = now.strftime("%Y-%m-%d")
    if ':' not in call.data:
        await callAnswer(call, '📅 这个签到按钮已过期，请重新打开菜单签到。', True)
        return
    else:
        _, date_str = call.data.split(':', 1)
        if date_str != today:
            await callAnswer(call, '📅 这个签到按钮已过期，请重新打开菜单签到。', True)
            return

    if config.open.checkin:
        e = await sql_get_emby(call.from_user.id)
        if not e:
            await callAnswer(call, '🧮 未查询到数据库', True)

        elif not e.ch or e.ch.strftime("%Y-%m-%d") < today:
            if config.open.checkin_lv:
                if e.lv > config.open.checkin_lv:
                    await callAnswer(call, f'❌ 您无权签到，如有异议，请不要有异议。', True)
                    return
            # 判断是否跨月，计算当月累计签到天数
            current_month = now.strftime("%Y-%m")
            last_month = e.ch.strftime("%Y-%m") if e.ch else ""
            if current_month == last_month:
                new_days = getattr(e, 'checkin_days', 0) + 1  # 兼容没及时迁移
            else:
                new_days = 1

            # 根据当月累计天数阶梯奖励
            if 1 <= new_days <= 15:
                reward = random.randint(3, 4)
            elif 16 <= new_days <= 27:
                reward = random.randint(4, 5)
            else:
                reward = random.randint(2, 3)

            s = e.iv + reward
            await sql_update_emby(Emby.tg == call.from_user.id, iv=s, ch=now, checkin_days=new_days)
            text = f'🎉 **签到成功** | 本月已签 `{new_days}` 天\n🎁 **获得奖励** | `{reward}` {config.money}\n💴 **当前持有** | `{s}` {config.money}\n⏳ **签到日期** | {now.strftime("%Y-%m-%d")}'
            await asyncio.gather(deleteMessage(call), sendMessage(call, text=text))

        else:
            await callAnswer(call, '⭕ 您今天已经签到过了，再签到剁掉你的小鸡鸡🐤。', True)
    else:
        await callAnswer(call, '❌ 未开启签到功能，等待！', True)
