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
