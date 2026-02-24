"""
游戏胜率统计管理器
提供游戏结算时的胜率数据更新和查询功能
"""
from typing import List, Dict, Optional
from bot.sql_helper.sql_emby import sql_get_emby, Session, Emby
from bot import LOGGER


class WinRateStatsManager:
    """游戏胜率统计管理器"""
    
    @staticmethod
    async def update_game_stats(player_results: List[Dict]) -> bool:
        """
        批量更新玩家游戏统计数据
        
        Args:
            player_results: 玩家结果列表，每个元素包含：
                - user_id: int - 用户TG ID
                - participated: bool - 是否参与（默认True）
                - won: bool - 是否获胜
        
        Returns:
            bool: 更新是否成功
        """
        if not player_results:
            LOGGER.warning("update_game_stats: 玩家结果列表为空")
            return True
        
        with Session() as session:
            try:
                # 构建批量更新数据
                mappings = []
                for result in player_results:
                    user_id = result.get('user_id')
                    participated = result.get('participated', True)
                    won = result.get('won', False)
                    
                    if not user_id:
                        LOGGER.warning(f"update_game_stats: 玩家结果缺少 user_id: {result}")
                        continue
                    
                    # 查询当前用户数据
                    user = session.query(Emby).filter(Emby.tg == user_id).first()
                    if not user:
                        LOGGER.warning(f"update_game_stats: 用户不存在: {user_id}")
                        continue
                    
                    # 计算新的统计值
                    new_played = user.game_played + (1 if participated else 0)
                    new_won = user.game_won + (1 if won else 0)
                    
                    # 数据一致性检查
                    if new_won > new_played:
                        LOGGER.error(
                            f"数据不一致: user_id={user_id}, "
                            f"new_won={new_won} > new_played={new_played}"
                        )
                        session.rollback()
                        return False
                    
                    mappings.append({
                        'tg': user_id,
                        'game_played': new_played,
                        'game_won': new_won
                    })
                
                if not mappings:
                    LOGGER.warning("update_game_stats: 没有有效的更新数据")
                    return True
                
                # 批量更新
                session.bulk_update_mappings(Emby, mappings)
                session.commit()
                
                LOGGER.info(
                    f"成功更新游戏统计: {len(mappings)} 个玩家, "
                    f"玩家ID: {[m['tg'] for m in mappings]}"
                )
                return True
                
            except Exception as e:
                LOGGER.error(
                    f"更新游戏统计失败: {e}, "
                    f"玩家: {[p.get('user_id') for p in player_results]}"
                )
                session.rollback()
                return False
    
    @staticmethod
    def get_user_stats(user_id: int) -> Optional[Dict]:
        """
        获取用户游戏统计数据
        
        Args:
            user_id: 用户TG ID
        
        Returns:
            Dict 包含：
                - game_played: int - 参与场次
                - game_won: int - 获胜场次
                - game_lost: int - 失败场次
                - win_rate: float - 胜率百分比
            或 None（用户不存在）
        """
        try:
            user = sql_get_emby(user_id)
            if not user:
                LOGGER.warning(f"get_user_stats: 用户不存在: {user_id}")
                return None
            
            game_played = user.game_played or 0
            game_won = user.game_won or 0
            game_lost = game_played - game_won
            
            # 计算胜率，处理除零情况
            if game_played == 0:
                win_rate = 0.0
            else:
                win_rate = (game_won / game_played) * 100
            
            return {
                'game_played': game_played,
                'game_won': game_won,
                'game_lost': game_lost,
                'win_rate': win_rate
            }
            
        except Exception as e:
            LOGGER.error(f"查询用户统计失败: {e}, user_id={user_id}")
            return None
    
    @staticmethod
    def format_win_rate(stats: Dict) -> str:
        """
        格式化胜率显示文本
        
        Args:
            stats: 统计数据字典
        
        Returns:
            str: 格式化的胜率文本，例如 "胜率: 65.50%"
        """
        if not stats:
            return ""
        
        win_rate = stats.get('win_rate', 0.0)
        return f"胜率: {win_rate:.2f}%"
    
    @staticmethod
    def format_stats_message(stats: Dict, username: str) -> str:
        """
        格式化完整的统计消息
        
        Args:
            stats: 统计数据字典
            username: 用户名
        
        Returns:
            str: 完整的统计报告文本
        """
        if not stats:
            return f"📊 {username} 的游戏统计\n\n暂无游戏记录，快去参与游戏吧！"
        
        game_played = stats.get('game_played', 0)
        game_won = stats.get('game_won', 0)
        game_lost = stats.get('game_lost', 0)
        win_rate = stats.get('win_rate', 0.0)
        
        if game_played == 0:
            return f"📊 {username} 的游戏统计\n\n暂无游戏记录，快去参与游戏吧！"
        
        message = f"📊 {username} 的游戏统计\n\n"
        message += f"🎮 总参与局数: {game_played}\n"
        message += f"🏆 总获胜局数: {game_won}\n"
        message += f"💔 总失败局数: {game_lost}\n"
        message += f"📈 胜率: {win_rate:.2f}%"
        
        return message

    @staticmethod
    def get_win_rate_leaderboard(limit: int = None) -> List[Dict]:
        """
        查询胜率排行榜

        Args:
            limit: 返回前 N 名玩家，None 表示返回所有符合条件的玩家

        Returns:
            List[Dict]: 排行榜数据列表，每个元素包含：
                - user_id: int - 用户TG ID
                - username: str - 用户名
                - game_played: int - 参与场次
                - game_won: int - 获胜场次
                - win_rate: float - 胜率百分比
        """
        try:
            with Session() as session:
                # 查询至少参与过 1 局游戏的玩家
                users = session.query(Emby).filter(
                    Emby.game_played >= 1
                ).all()

                if not users:
                    LOGGER.info("get_win_rate_leaderboard: 暂无符合条件的玩家")
                    return []

                # 计算胜率并构建排行榜数据
                leaderboard = []
                for user in users:
                    win_rate = (user.game_won / user.game_played) * 100
                    leaderboard.append({
                        'user_id': user.tg,
                        'username': user.name or "未知用户",
                        'game_played': user.game_played,
                        'game_won': user.game_won,
                        'win_rate': win_rate
                    })

                # 按胜率降序排序
                leaderboard.sort(key=lambda x: x['win_rate'], reverse=True)

                # 返回前 N 名或全部
                if limit is not None:
                    result = leaderboard[:limit]
                else:
                    result = leaderboard
                    
                LOGGER.info(f"成功查询排行榜: 共 {len(result)} 名玩家")
                return result

        except Exception as e:
            LOGGER.error(f"查询排行榜失败: {e}")
            return []

    @staticmethod
    def format_leaderboard_message(leaderboard: List[Dict], page: int = 1, total_pages: int = 1, start_rank: int = 0) -> str:
        """
        格式化排行榜消息

        Args:
            leaderboard: 排行榜数据列表
            page: 当前页码
            total_pages: 总页数
            start_rank: 起始排名（用于计算实际排名）

        Returns:
            str: 格式化的排行榜文本
        """
        if not leaderboard:
            return "🏆 胜率排行榜\n\n暂无排行数据（至少参与 1 局游戏）"

        message = "🏆 胜率排行榜\n"
        message += "（至少参与 1 局游戏）\n\n"

        # 排名表情符号
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}

        for idx, player in enumerate(leaderboard, start=1):
            # 计算实际排名
            actual_rank = start_rank + idx

            # 前三名使用奖牌，其他使用数字
            rank_symbol = medals.get(actual_rank, f"{actual_rank}.")

            username = player['username']
            user_id = player['user_id']
            win_rate = player['win_rate']
            game_played = player['game_played']
            game_won = player['game_won']

            # 格式化用户名（使用 Markdown 链接）
            user_link = f"[{username}](tg://user?id={user_id})"

            # 构建排行信息
            message += f"{rank_symbol} {user_link}\n"
            message += f"   📈 胜率: {win_rate:.2f}% | 🎮 {game_won}/{game_played} 胜\n\n"

        # 添加分页信息
        message += f"\n第 {page} 页，共 {total_pages} 页"

        return message.strip()

