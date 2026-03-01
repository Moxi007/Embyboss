import asyncio
import os

import aiohttp
from pyrogram import filters
from pyrogram.types import Message

from bot import LOGGER, bot, config, prefixes, save_config
from bot.func_helper.filters import admins_on_filter, user_in_group_on_filter
from bot.func_helper.fix_bottons import sched_buttons, plays_list_button
from bot.func_helper.msg_utils import callAnswer, editMessage, deleteMessage
from bot.func_helper.scheduler import scheduler
from bot.scheduler import *


# 初始化命令 开机检查重启
loop = asyncio.get_event_loop()
loop.call_later(5, lambda: loop.create_task(BotCommands.set_commands(client=bot)))
loop.call_later(5, lambda: loop.create_task(check_restart()))

# 启动定时任务
auto_backup_db = DbBackupUtils.auto_backup_db
user_plays_rank = Uplaysinfo.user_plays_rank
check_low_activity = Uplaysinfo.check_low_activity

async def user_day_plays(): await user_plays_rank(1)


async def user_week_plays(): await user_plays_rank(7)


# 写优雅点
# 字典，method相应的操作函数
action_dict = {
    "dayrank": day_ranks,
    "weekrank": week_ranks,
    "dayplayrank": user_day_plays,
    "weekplayrank": user_week_plays,
    "check_ex": check_expired,
    "low_activity": check_low_activity,
    "backup_db": auto_backup_db,
}

# 字典，对应的操作函数的参数和id
args_dict = {
    "dayrank": {'hour': 18, 'minute': 30, 'id': 'day_ranks'},
    "weekrank": {'day_of_week': "sun", 'hour': 23, 'minute': 59, 'id': 'week_ranks'},
    "dayplayrank": {'hour': 23, 'minute': 0, 'id': 'user_day_plays'},
    "weekplayrank": {'day_of_week': "sun", 'hour': 23, 'minute': 0, 'id': 'user_week_plays'},
    "check_ex": {'hour': 1, 'minute': 30, 'id': 'check_expired'},
    "low_activity": {'hour': 8, 'minute': 30, 'id': 'check_low_activity'},
    "backup_db": {'hour': 2, 'minute': 30, 'id': 'backup_db'},
}


def set_all_sche():
    for key, value in action_dict.items():
        if getattr(config.schedall, key):
            action = action_dict[key]
            args = args_dict[key]
            scheduler.add_job(action, 'cron', **args)


set_all_sche()


# 配置文件自动热重载监控（每10秒检查一次 config.json 是否被外部修改）
async def _config_file_watcher():
    """自动检测 config.json 文件变化并热重载"""
    if config.reload_from_file():
        LOGGER.info("【热重载】检测到 config.json 变更，已自动重载配置")

scheduler.add_job(_config_file_watcher, 'interval', seconds=10, id='config_file_watcher')


async def sched_panel(_, msg):
    # await deleteMessage(msg)
    await editMessage(msg,
                      text=f'🎮 **管理定时任务面板**\n\n',
                      buttons=sched_buttons())


@bot.on_callback_query(filters.regex('sched') & admins_on_filter)
async def sched_change_policy(_, call):
    try:
        method = call.data.split('-')[1]
        # 根据method的值来添加或移除相应的任务
        action = action_dict[method]
        args = args_dict[method]
        if getattr(config.schedall, method):
            scheduler.remove_job(job_id=args['id'], jobstore='default')
        else:
            scheduler.add_job(action, 'cron', **args)
        setattr(config.schedall, method, not getattr(config.schedall, method))
        save_config()
        await asyncio.gather(callAnswer(call, f'⭕️ {method} 更改成功'), sched_panel(_, call.message))
    except IndexError:
        await sched_panel(_, call.message)


@bot.on_message(filters.command('check_ex', prefixes) & admins_on_filter)
async def check_ex_admin(_, msg):
    await deleteMessage(msg)
    confirm = False
    try:
        confirm = msg.command[1]
    except:
        pass
    if confirm == 'true':
        send = await msg.reply("🍥 正在运行 【到期检测】。。。")
        await asyncio.gather(check_expired(), send.edit("✅ 【到期检测结束】"))
    else:
        await msg.reply("🔔 请输入 `/check_ex true` 确认运行")


# bot数据库手动备份
@bot.on_message(filters.command('backup_db', prefixes) & filters.user(config.owner))
async def manual_backup_db(_, msg):
    await asyncio.gather(deleteMessage(msg), auto_backup_db())


@bot.on_message(filters.command('days_ranks', prefixes) & admins_on_filter)
async def day_r_ranks(_, msg):
    await asyncio.gather(msg.delete(), day_ranks(pin_mode=False))


@bot.on_message(filters.command('week_ranks', prefixes) & admins_on_filter)
async def week_r_ranks(_, msg):
    await asyncio.gather(msg.delete(), week_ranks(pin_mode=False))


@bot.on_message(filters.command('low_activity', prefixes) & admins_on_filter)
async def run_low_ac(_, msg):
    await deleteMessage(msg)
    confirm = False
    try:
        confirm = msg.command[1]
    except:
        pass
    if confirm == 'true':
        send = await msg.reply("⭕ 不活跃检测运行ing···")
        await asyncio.gather(check_low_activity(), send.delete())
    else:
        await msg.reply("🔔 请输入 `/low_activity true` 确认运行")

@bot.on_message(filters.command('uranks', prefixes) & admins_on_filter)
async def shou_dong_uplayrank(_, msg):
    await deleteMessage(msg)
    try:
        days = int(msg.command[1])
        await user_plays_rank(days=days, uplays=False)
    except (IndexError, ValueError):
        await msg.reply(
            f"🔔 请输入 `/uranks 天数`，此运行手动不会影响{config.money}的结算（仅定时运行时结算），放心使用。\n"
            f"定时结算状态: {config.open.uplays}")
@bot.on_message(filters.command('sync_favorites', prefixes) & admins_on_filter)
async def sync_favorites_admin(_, msg):
    await deleteMessage(msg)
    await msg.reply("⭕ 正在同步用户收藏记录...")
    await sync_favorites()
    await msg.reply("✅ 用户收藏记录同步完成")

@bot.on_message(filters.command('restart', prefixes) & admins_on_filter)
async def restart_bot(_, msg):
    await deleteMessage(msg)
    send = await msg.reply("Restarting，等待几秒钟。")
    config.schedall.restart_chat_id = send.chat.id
    config.schedall.restart_msg_id = send.id
    save_config()
    LOGGER.info("手动重启")
    import os, sys
    # 确保在项目根目录启动
    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    os.execv(sys.executable, [sys.executable, 'main.py'])


@bot.on_callback_query(filters.regex('uranks') & user_in_group_on_filter)
async def page_uplayrank(_, call):
    j, days = map(int, call.data.split(":")[1].split('_'))
    await callAnswer(call, f'将为您翻到第 {j} 页')
    a, b, c = await Uplaysinfo.users_playback_list(days)
    if not a:
        return await callAnswer(call, f'🍥 获取过去{days}天UserPlays失败了嘤嘤嘤 ~ 手动重试', True)
    button = await plays_list_button(b, j, days)
    text = a[j - 1]
    await editMessage(call, text, buttons=button)


from asyncio import create_subprocess_shell

from asyncio.subprocess import PIPE


async def execute(command, pass_error=True):
    """执行"""
    executor = await create_subprocess_shell(
        command, stdout=PIPE, stderr=PIPE, stdin=PIPE
    )

    stdout, stderr = await executor.communicate()
    if pass_error:
        try:
            result = str(stdout.decode().strip()) + str(stderr.decode().strip())
        except UnicodeDecodeError:
            result = str(stdout.decode("gbk").strip()) + str(stderr.decode("gbk").strip())
    else:
        try:
            result = str(stdout.decode().strip())
        except UnicodeDecodeError:
            result = str(stdout.decode("gbk").strip())
    return result


from sys import executable, argv


@scheduler.SCHEDULER.scheduled_job('cron', hour='12', minute='30', id='update_bot')
async def update_bot(force: bool = False, msg: Message = None, manual: bool = False):
    """
    此为未被测试的代码片段。
    """
    # print("update")
    if not config.auto_update.status and not manual: return
    branch = config.auto_update.git_branch or "beta"
    commit_url = f"https://api.github.com/repos/{config.auto_update.git_repo}/commits?sha={branch}&per_page=1"
    async with aiohttp.ClientSession() as session:
        async with session.get(commit_url) as resp:
            if resp.status == 200:
                data = await resp.json()
                latest_commit = data[0]["sha"]
                if latest_commit != config.auto_update.commit_sha:
                    up_description = data[0]["commit"]["message"]
                    await execute("git fetch --all")
                    
                    # 强制切换分支并硬重置，防止冲突
                    await execute(f"git checkout {branch}")
                    await execute(f"git reset --hard origin/{branch}")
                    await execute(f"git pull origin {branch}")
                    
                    # 清除 Python 字节码缓存和未跟踪的文件，确保重启后加载全新纯净的代码
                    await execute("git clean -fd") 
                    await execute("find . -name '*.pyc' -delete")
                    await execute("find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true")
                    
                    await execute(f"{executable} -m pip install -r requirements.txt")
                    text = '【AutoUpdate_Bot】运行成功，已拉取并更新 bot 代码。正在执行热重启...'
                    if not msg:
                        reply = await bot.send_message(chat_id=config.group[0], text=text)
                        config.schedall.restart_chat_id = config.group[0]
                        config.schedall.restart_msg_id = reply.id
                    else:
                        await msg.edit(text)
                    LOGGER.info(text)
                    config.auto_update.commit_sha = latest_commit
                    config.auto_update.up_description = up_description
                    save_config()
                    
                    # 使用 os.execv 携带当前环境让当前解释器重新执行 main.py
                    import os, sys
                    LOGGER.info("更新操作完成，正在进行 os.execv 重启...")
                    # 确保在项目根目录启动
                    os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
                    os.execv(sys.executable, [sys.executable, 'main.py'])
                else:
                    message = "【AutoUpdate_Bot】运行成功，未检测到更新，结束"
                    await bot.send_message(chat_id=config.group[0], text=message) if not msg else await msg.edit(message)
                    LOGGER.info(message)
            else:
                text = '【AutoUpdate_Bot】失败，请检查 git_repo 是否正确，形如 `berry8838/Sakura_embyboss`'
                await bot.send_message(chat_id=config.group[0], text=text) if not msg else await msg.edit(text)
                LOGGER.info(text)


@bot.on_message(filters.command('update_bot', prefixes) & admins_on_filter)
async def get_update_bot(_, msg: Message):
    delete_task = msg.delete()
    send_task = bot.send_message(chat_id=msg.chat.id, text='正在更新bot代码，请稍等。。。')
    results = await asyncio.gather(delete_task, send_task)
    # results[1] 是发送消息的结果，从中提取 chat_id 和 message_id
    if len(results) == 2 and isinstance(results[1], Message):
        reply = results[1]
        config.schedall.restart_chat_id = reply.chat.id
        config.schedall.restart_msg_id = reply.id
        save_config()
        await update_bot(msg=reply, manual=True)