import math
import cn2an
from datetime import datetime, timezone, timedelta

from bot import LOGGER, bot, config 
from bot.func_helper.emby import emby
from bot.func_helper.utils import convert_to_beijing_time, convert_s, cache, get_users, tem_deluser
from bot.sql_helper import Session
from sqlalchemy import select
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_embys, Emby, sql_update_emby
from bot.func_helper.fix_bottons import plays_list_button


class Uplaysinfo:
    client = emby

    @classmethod
    @cache.memoize(ttl=120)
    async def users_playback_list(cls, days):
        try:
            play_list = await emby.emby_cust_commit(emby_id=None, days=days, method='sp')
        except Exception as e:
            print(f"Error fetching playback list: {e}")
            return None, 1, 1

        if play_list is None:
            return None, 1, 1

        async with Session() as session:
            # 更高效地查询 Emby 表的数据
            result_db = await session.execute(select(Emby).filter(Emby.name.isnot(None)))
            result = result_db.scalars().all()

            if not result:
                return None, 1

            total_pages = math.ceil(len(play_list) / 10)
            members = await get_users()
            members_dict = {}

            for record in result:
                members_dict[record.name] = {
                    "name": members.get(record.tg, record.name),
                    "tg": record.tg,
                    "lv": record.lv,
                    "iv": record.iv
                }

            rank_medals = ["🥇", "🥈", "🥉", "🏅"]
            rank_points = [1000, 900, 800, 700, 600, 500, 400, 300, 200, 100]

            pages_data = []
            leaderboard_data = []

            for page_number in range(1, total_pages + 1):
                start_index = (page_number - 1) * 10
                end_index = start_index + 10
                page_data = f'**▎🏆{config.ranks.logo} {days} 天观影榜**\n\n'

                for rank, play_record in enumerate(play_list[start_index:end_index], start=start_index + 1):
                    medal = rank_medals[rank - 1] if rank < 4 else rank_medals[3]
                    member_info = members_dict.get(play_record[0], None)

                    if not member_info or not member_info["tg"]:
                        emby_name = '神秘客户' 
                        # emby_name = play_record[0] + ' (未绑定Bot)'
                        tg = 'None'
                    else:
                        emby_name = member_info["name"]
                        tg = member_info["tg"]

                        # 计算积分
                        points = rank_points[rank - 1] + (int(play_record[1]) // 60) if rank <= 10 else (
                                    int(play_record[1]) // 60)
                        new_iv = member_info["iv"] + points
                        leaderboard_data.append([member_info["tg"], new_iv, f'{medal}{emby_name}', points])

                    formatted_time = await convert_s(int(play_record[1]))
                    page_data += f'{medal}**第{cn2an.an2cn(rank)}名** | [{emby_name}](tg://user?id={tg})\n' \
                                 f'  观影时长 | {formatted_time}\n'

                page_data += f'\n#UPlaysRank {datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")}'
                pages_data.append(page_data)

            return pages_data, total_pages, leaderboard_data

    @staticmethod
    async def user_plays_rank(days=7, uplays=True):
        a, n, ls = await Uplaysinfo.users_playback_list(days)
        if not a:
            return await bot.send_photo(chat_id=config.group[0], photo=config.bot_photo,
                                        caption=f'🍥 获取过去{days}天UserPlays失败了嘤嘤嘤 ~ 手动重试 ')
        play_button = await plays_list_button(n, 1, days)
        send = await bot.send_photo(chat_id=config.group[0], photo=config.bot_photo, caption=a[0], reply_markup=play_button)
        if uplays and config.open.uplays:
            if await sql_update_embys(some_list=ls, method='iv'):
                text = f'**自动将观看时长转换为{config.money}**\n\n'
                for i in ls:
                    text += f'[{i[2]}](tg://user?id={i[0]}) 获得了 {i[3]} {config.money}奖励\n'
                n = 4096
                chunks = [text[i:i + n] for i in range(0, len(text), n)]
                for c in chunks:
                    await bot.send_message(chat_id=config.group[0],
                                           text=c + f'\n⏱️ 当前时间 - {datetime.now().strftime("%Y-%m-%d")}')
                LOGGER.info(f'【userplayrank】： ->成功 数据库执行批量操作{ls}')
            else:
                await send.reply(f'**🎂！！！为用户增加{config.money}出错啦** @工程师看看吧~ ')
                LOGGER.error(f'【userplayrank】：-？失败 数据库执行批量操作{ls}')

    @staticmethod
    async def check_low_activity(watch_threshold_hours: int = None):
        now = datetime.now(timezone(timedelta(hours=8)))
        success, users = await emby.users()
        if not success:
            return await bot.send_message(chat_id=config.group[0], text='⭕ 调用emby api失败')
        from bot import config
        activity_check_days = config.activity_check_days
        msg = f'正在执行**{activity_check_days}天活跃检测**...\n'
        for user in users:
            # 数据库先找
            e = await sql_get_emby(tg=user["Name"])
            if e is None:
                continue

            elif e.lv == 'c':
                try:
                    ac_date = convert_to_beijing_time(user["LastActivityDate"])
                except KeyError:
                    ac_date = "None"
                finally:
                    if ac_date == "None" or ac_date + timedelta(days=15) < now:
                        if await emby.emby_del(emby_id=e.embyid):
                            await sql_update_emby(Emby.embyid == e.embyid, embyid=None, name=None, pwd=None, pwd2=None, lv='d',
                                            cr=None, ex=None)
                            tem_deluser()
                            msg += f'**🔋活跃检测** - [{e.name}](tg://user?id={e.tg})\n#id{e.tg} 禁用后未解禁，已执行删除。\n\n'
                            LOGGER.info(f"【活跃检测】- 删除账户 {user['Name']} #id{e.tg}")
                        else:
                            msg += f'**🔋活跃检测** - [{e.name}](tg://user?id={e.tg})\n#id{e.tg} 禁用后未解禁，执行删除失败。\n\n'
                            LOGGER.info(f"【活跃检测】- 删除账户失败 {user['Name']} #id{e.tg}")
            elif e.lv == 'b':
                try:
                    ac_date = convert_to_beijing_time(user["LastActivityDate"])
                    
                    # 1. 检测长期未登录（原逻辑）
                    if ac_date + timedelta(days=activity_check_days) < now:
                        if await emby.emby_change_policy(emby_id=user["Id"], disable=True):
                            await sql_update_emby(Emby.embyid == user["Id"], lv='c')
                            msg += f"**🔋活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} {activity_check_days}天未活跃，禁用\n\n"
                            LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：{activity_check_days}天未活跃")
                        else:
                            msg += f"**🎂活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n{activity_check_days}天未活跃，禁用失败啦！检查emby连通性\n\n"
                            LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：禁用失败啦！检查emby连通性")
                        continue  # 已经被第一项规则禁用，跳过时长检测
                    
                    # 2. 检测近 30 天内观看时长是否达标 (新逻辑)
                    if watch_threshold_hours is None:
                        watch_threshold_hours = config.schedall.low_activity_watch_hours
                    if watch_threshold_hours > 0:
                        # 增加判断：注册是否已满 30 天
                        try:
                            created_date = convert_to_beijing_time(user["DateCreated"])
                            if created_date + timedelta(days=30) > now:
                                continue  # 注册未满 30 天，跳过此时长检测，给新人缓冲期
                        except KeyError:
                            pass # 拿不到创建时间就暂时放开或按老方式继续往下查

                        # 使用 Emby 查询过去 30 天的时长数据
                        play_stats = await emby.emby_cust_commit(emby_id=user["Id"], days=30)
                        
                        # 返回的 play_stats 预期为只包含一行的列表，例如 [{"LastLogin": "...", "WatchTime": 120}]，WatchTime单位为分钟
                        watch_time_mins = 0
                        if play_stats and len(play_stats) > 0 and play_stats[0].get("WatchTime"):
                            watch_time_mins = int(play_stats[0].get("WatchTime", 0))
                        
                        watch_time_hours = watch_time_mins / 60
                        if watch_time_hours < watch_threshold_hours:
                            if await emby.emby_change_policy(emby_id=user["Id"], disable=True):
                                await sql_update_emby(Emby.embyid == user["Id"], lv='c')
                                msg += f"**🔋活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} 过去30天观看时长不足{watch_threshold_hours}小时(当前{watch_time_hours:.1f}时)，禁用\n\n"
                                LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：30天内播放时长不足")
                            else:
                                msg += f"**🎂活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n由于播放时长不足禁用失败啦！检查emby连通性\n\n"
                                LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：由于播放时长不足禁用失败")
                            continue
                            
                except KeyError:
                    # 注册后未曾有过任何活动
                    if await emby.emby_change_policy(emby_id=user["Id"], disable=True):
                        await sql_update_emby(Emby.embyid == user["Id"], lv='c')
                        msg += f"**🔋活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} 注册后未活跃，禁用\n\n"
                        LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：注册后未活跃禁用")
                    else:
                        msg += f"**🎂活跃检测** - [{user['Name']}](tg://user?id={e.tg})\n#id{e.tg} 注册后未活跃，禁用失败啦！检查emby连通性\n\n"
                        LOGGER.info(f"【活跃检测】- 禁用账户 {user['Name']} #id{e.tg}：禁用失败啦！检查emby连通性")
        msg += '**活跃检测结束**\n'
        n = 1000
        chunks = [msg[i:i + n] for i in range(0, len(msg), n)]
        for c in chunks:
            await bot.send_message(chat_id=config.group[0], text=c + f'**{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**')
