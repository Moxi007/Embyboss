"""
多人21点游戏模块

支持1-20人同时参与的多人21点游戏，采用并行异步操作模式。
玩家可以在同一局游戏中与庄家进行对战，无需等待其他玩家回合。
"""

import asyncio
import random
import time
from typing import Dict, List, Tuple, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from pyrogram.errors import FloodWait, MessageDeleteForbidden

from bot import LOGGER
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby
from bot.schemas.schemas import Config

# 导入 bot 实例用于注册处理器
from bot import bot, prefixes


# ==================== 21点游戏核心逻辑类 ====================

class G21Logic:
    """21点游戏核心逻辑类"""
    
    # 扑克牌花色
    SUITS = ['♠', '♥', '♣', '♦']
    
    # 扑克牌点数
    RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

    
    @staticmethod
    def create_deck() -> List[str]:
        """
        创建并洗牌
        
        使用 Fisher-Yates 洗牌算法确保随机性
        
        返回:
            洗好的牌堆列表
        """
        # 创建完整牌组
        deck = [f"{suit}{rank}" for suit in G21Logic.SUITS for rank in G21Logic.RANKS]
        
        # Fisher-Yates 洗牌算法
        for i in range(len(deck) - 1, 0, -1):
            j = random.randint(0, i)
            deck[i], deck[j] = deck[j], deck[i]
        
        return deck
    
    @staticmethod
    def deal_card(deck: List[str]) -> str:
        """
        从牌堆抽一张牌
        
        参数:
            deck: 牌堆列表
        
        返回:
            抽取的牌
        """
        if deck:
            return deck.pop()
        return None

    
    @staticmethod
    def calculate_points(cards: List[str]) -> int:
        """
        计算手牌总点数（21点规则）
        
        规则:
            - A: 1或11（灵活计算，优先计为11，如果爆牌则计为1）
            - 2-10: 牌面点数
            - J/Q/K: 10点
        
        参数:
            cards: 手牌列表
        
        返回:
            总点数（整数）
        """
        total = 0
        ace_count = 0
        
        for card in cards:
            # 去掉花色符号，获取点数
            rank = card[1:]
            if rank == 'A':
                ace_count += 1
                total += 11  # 先按11计算
            elif rank in ['J', 'Q', 'K']:
                total += 10
            else:
                total += int(rank)
        
        # 如果有A且总点数超过21，将A从11改为1
        while total > 21 and ace_count > 0:
            total -= 10  # 将一个A从11改为1（差值为10）
            ace_count -= 1
        
        return total

    
    @staticmethod
    def dealer_auto_draw(dealer_cards: List[str], deck: List[str]) -> List[str]:
        """
        庄家自动抽牌逻辑（21点规则）
        
        规则: 点数 < 17 时继续抽牌
        
        参数:
            dealer_cards: 庄家当前手牌
            deck: 剩余牌堆
        
        返回:
            更新后的庄家手牌
        """
        while True:
            points = G21Logic.calculate_points(dealer_cards)
            
            # 停止条件：点数达到17或以上、爆牌（>21）、或达到5张牌
            if points >= 17 or points > 21 or len(dealer_cards) >= 5:
                break
            
            # 抽牌
            if deck:
                card = G21Logic.deal_card(deck)
                if card:
                    dealer_cards.append(card)
                else:
                    break
            else:
                break  # 牌堆空了
        
        return dealer_cards

    
    @staticmethod
    def judge_winner(player_points: int, dealer_points: int,
                     player_cards: List[str], dealer_cards: List[str]) -> dict:
        """
        判定胜负（21点规则）
        
        参数:
            player_points: 玩家点数
            dealer_points: 庄家点数
            player_cards: 玩家手牌
            dealer_cards: 庄家手牌
        
        返回:
            包含胜负信息的字典:
            {
                'winner': 'player' | 'dealer' | 'tie',
                'reason': str,
                'multiplier': float,
                'player_points': int,
                'dealer_points': int,
                'is_five_dragon': bool
            }
        """
        result = {
            'player_points': player_points,
            'dealer_points': dealer_points,
            'multiplier': 0.0,
            'is_five_dragon': False
        }
        
        # 1. 玩家爆牌
        if player_points > 21:
            result['winner'] = 'dealer'
            result['reason'] = '玩家爆牌'
            return result
        
        # 2. 玩家五小龙
        if len(player_cards) == 5 and player_points <= 21:
            result['is_five_dragon'] = True
            if len(dealer_cards) != 5 or dealer_points > 21:
                result['winner'] = 'player'
                result['reason'] = '玩家五小龙'
                result['multiplier'] = 2.0
                return result
        
        # 3. 庄家爆牌
        if dealer_points > 21:
            result['winner'] = 'player'
            result['reason'] = '庄家爆牌'
            result['multiplier'] = 1.0
            return result
        
        # 4. 庄家五小龙
        if len(dealer_cards) == 5 and dealer_points <= 21:
            result['winner'] = 'dealer'
            result['reason'] = '庄家五小龙'
            return result
        
        # 5. 比较点数
        if player_points > dealer_points:
            result['winner'] = 'player'
            result['reason'] = '点数较大'
            result['multiplier'] = 1.0
        elif player_points < dealer_points:
            result['winner'] = 'dealer'
            result['reason'] = '点数较小'
        else:
            result['winner'] = 'tie'
            result['reason'] = '点数相同'
            result['multiplier'] = 1.0  # 退还本金
        
        return result


def format_card(card: str, hidden: bool = False) -> str:
    """
    格式化牌面显示
    
    参数:
        card: 牌（如 '♠A'）
        hidden: 是否隐藏
    
    返回:
        格式化的字符串
    """
    if hidden:
        return "🂠"  # 牌背
    return card


def format_hand(cards: List[str], hide_second: bool = False) -> str:
    """
    格式化手牌显示
    
    参数:
        cards: 手牌列表
        hide_second: 是否隐藏第二张牌
    
    返回:
        格式化的字符串
    """
    result = []
    for i, card in enumerate(cards):
        if i == 1 and hide_second:
            result.append(format_card(card, hidden=True))
        else:
            result.append(format_card(card))
    return " ".join(result)


# ==================== 全局状态存储 ====================

# 活跃的多人游戏会话 (group_id -> MultiplayerG21Session)
active_multiplayer_g21_games: Dict[int, 'MultiplayerG21Session'] = {}

# 玩家操作锁，防止并发操作导致数据不一致 ((group_id, user_id) -> Lock)
player_operation_locks: Dict[Tuple[int, int], asyncio.Lock] = {}


# ==================== 常量定义 ====================

class GamePhase:
    """游戏阶段常量"""
    LOBBY = "LOBBY"           # 筹备阶段
    ACTION = "ACTION"         # 操作阶段
    RESOLUTION = "RESOLUTION" # 结算阶段


class PlayerState:
    """玩家状态常量"""
    PLAYING = "PLAYING"           # 操作中
    STAND = "STAND"               # 已停牌
    BUST = "BUST"                 # 已爆牌
    BLACKJACK = "BLACKJACK"       # Blackjack（起手21点）
    FIVE_DRAGON = "FIVE_DRAGON"   # 五小龙（5张牌且不超过21点）


# ==================== 指令解析器 ====================

class CommandParser:
    """游戏指令解析器"""
    
    @staticmethod
    def parse_g21_command(command_text: str, user_balance: int) -> dict:
        """
        解析 /g21 指令
        
        参数:
            command_text: 指令文本（如 "/g21 100" 或 "/g21 all"）
            user_balance: 用户当前余额
            
        返回:
            dict: {
                "success": bool,
                "bet_amount": int,
                "error_message": str
            }
        """
        parts = command_text.strip().split()
        
        # 检查指令格式
        if len(parts) < 2:
            return {
                "success": False,
                "bet_amount": 0,
                "error_message": "指令格式错误，正确格式：/g21 [金额] 或 /g21 all"
            }
        
        bet_str = parts[1].lower()
        
        # 处理 "all" 梭哈指令
        if bet_str == "all":
            return {
                "success": True,
                "bet_amount": user_balance,
                "error_message": ""
            }
        
        # 处理数字金额
        try:
            bet_amount = int(bet_str)
            if bet_amount <= 0:
                return {
                    "success": False,
                    "bet_amount": 0,
                    "error_message": "下注金额必须为正整数"
                }
            return {
                "success": True,
                "bet_amount": bet_amount,
                "error_message": ""
            }
        except ValueError:
            return {
                "success": False,
                "bet_amount": 0,
                "error_message": "下注金额格式错误，请输入数字或 'all'"
            }


# ==================== 看板渲染器 ====================

class ScoreboardRenderer:
    """游戏状态看板渲染器"""
    
    @staticmethod
    def render_lobby(players: List[dict], countdown: int) -> str:
        """
        渲染筹备阶段消息
        
        参数:
            players: 玩家列表
            countdown: 倒计时秒数
            
        返回:
            str: 格式化后的消息文本
        """
        lines = [
            "🎰 **多人21点游戏 - 筹备阶段**",
            "",
            f"⏱ 倒计时：**{countdown}** 秒",
            f"👥 当前玩家数：**{len(players)}**",
            "",
            "📋 **玩家列表：**"
        ]
        
        for i, player in enumerate(players, 1):
            lines.append(f"{i}. {player['username']} - 下注 **{player['bet_amount']}** 金币")
        
        lines.append("")
        lines.append("💡 发送 `/g21 [金额]` 加入游戏")
        lines.append("💡 点击下方按钮可退出并退款")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_scoreboard(dealer_cards: List[str], players: List[dict], 
                         countdown: int, hide_dealer_second: bool = True) -> str:
        """
        渲染操作阶段看板
        
        参数:
            dealer_cards: 庄家手牌
            players: 玩家列表
            countdown: 倒计时秒数
            hide_dealer_second: 是否隐藏庄家第二张牌
            
        返回:
            str: 格式化后的消息文本
        """
        lines = [
            "🎰 **多人21点游戏 - 操作阶段**",
            "",
            f"⏱ 剩余时间：**{countdown}** 秒",
            "",
            "🎴 **庄家手牌：**"
        ]
        
        # 显示庄家手牌
        dealer_hand = format_hand(dealer_cards, hide_second=hide_dealer_second)
        if hide_dealer_second:
            dealer_points = G21Logic.calculate_points([dealer_cards[0]])
            lines.append(f"{dealer_hand} (明牌点数：{dealer_points})")
        else:
            dealer_points = G21Logic.calculate_points(dealer_cards)
            lines.append(f"{dealer_hand} (点数：{dealer_points})")
        
        lines.append("")
        lines.append("👥 **玩家状态：**")
        
        # 显示所有玩家状态
        for i, player in enumerate(players, 1):
            player_hand = format_hand(player['cards'])
            points = player['points']
            state = player['state']
            
            # 状态图标
            state_icon = {
                PlayerState.PLAYING: "🎮",
                PlayerState.STAND: "🛑",
                PlayerState.BUST: "💥",
                PlayerState.BLACKJACK: "⭐",
                PlayerState.FIVE_DRAGON: "🐉"
            }.get(state, "❓")
            
            # 状态文字
            state_text = {
                PlayerState.PLAYING: "操作中",
                PlayerState.STAND: "已停牌",
                PlayerState.BUST: "已爆牌",
                PlayerState.BLACKJACK: "Blackjack",
                PlayerState.FIVE_DRAGON: "五小龙"
            }.get(state, "未知")
            
            lines.append(
                f"{i}. {state_icon} **{player['username']}** "
                f"(下注 {player['bet_amount']})"
            )
            lines.append(f"   手牌：{player_hand} | 点数：**{points}** | {state_text}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_settlement(results: List[dict], dealer_cards: List[str]) -> str:
        """
        渲染结算消息
        
        参数:
            results: 结算结果列表
            dealer_cards: 庄家最终手牌
            
        返回:
            str: 格式化后的消息文本
        """
        dealer_hand = format_hand(dealer_cards)
        dealer_points = G21Logic.calculate_points(dealer_cards)
        
        lines = [
            "🎰 **多人21点游戏 - 结算**",
            "",
            "🎴 **庄家最终手牌：**",
            f"{dealer_hand} (点数：{dealer_points})",
            "",
            "📊 **结算结果：**"
        ]
        
        for i, result in enumerate(results, 1):
            username = result['username']
            bet_amount = result['bet_amount']
            game_result = result['result']
            payout = result['payout']
            player_points = result['player_points']
            
            # 结果图标和文字
            if game_result == "WIN":
                icon = "🎉"
                result_text = "获胜"
                win_type = result.get('win_type', 'NORMAL')
                if win_type == "BLACKJACK":
                    result_text += " (Blackjack)"
                elif win_type == "FIVE_DRAGON":
                    result_text += " (五小龙)"
                coin_change = f"+{bet_amount + payout}"
            elif game_result == "LOSE":
                icon = "😢"
                result_text = "失败"
                coin_change = f"-{bet_amount}"
            else:  # DRAW
                icon = "🤝"
                result_text = "平局"
                coin_change = "±0"
            
            lines.append(
                f"{i}. {icon} **{username}** - {result_text} "
                f"(点数：{player_points}) | 金币变化：**{coin_change}**"
            )
        
        lines.append("")
        lines.append("💡 本消息将在 180 秒后自动删除")
        
        return "\n".join(lines)


# ==================== 游戏会话管理类 ====================

class MultiplayerG21Session:
    """多人21点游戏会话管理器"""
    
    def __init__(self, group_id: int):
        """
        初始化游戏会话
        
        参数:
            group_id: 群组ID
        """
        self.group_id = group_id
        self.phase = GamePhase.LOBBY
        self.players: List[dict] = []
        self.dealer_cards: List[str] = []
        self.deck: List[str] = []
        
        # 消息ID
        self.lobby_message_id: Optional[int] = None
        self.scoreboard_message_id: Optional[int] = None
        
        # 异步任务
        self.countdown_task: Optional[asyncio.Task] = None
        self.update_task: Optional[asyncio.Task] = None
        
        # 时间戳和超时配置
        self.created_at = time.time()
        config = Config.load_config()
        self.lobby_timeout = config.game.multiplayer_g21_lobby_timeout
        self.action_timeout = config.game.multiplayer_g21_action_timeout
        self.lobby_remaining = self.lobby_timeout
        self.action_remaining = self.action_timeout
        
        LOGGER.info(f"创建多人21点游戏会话 - 群组ID: {group_id}")
    
    def get_player(self, user_id: int) -> Optional[dict]:
        """
        根据用户ID获取玩家
        
        参数:
            user_id: 用户ID
            
        返回:
            玩家字典或None
        """
        for player in self.players:
            if player['user_id'] == user_id:
                return player
        return None
    
    def is_player_in_game(self, user_id: int) -> bool:
        """
        检查玩家是否在游戏中
        
        参数:
            user_id: 用户ID
            
        返回:
            bool
        """
        return self.get_player(user_id) is not None
    
    async def add_player(self, user_id: int, username: str, bet_amount: int) -> dict:
        """
        添加玩家到游戏会话
        
        参数:
            user_id: 用户ID
            username: 用户名
            bet_amount: 下注金额
            
        返回:
            dict: {"success": bool, "message": str}
        """
        # 检查游戏阶段
        if self.phase != GamePhase.LOBBY:
            return {"success": False, "message": "游戏已开始，无法加入"}
        
        # 检查玩家是否已在游戏中
        if self.is_player_in_game(user_id):
            return {"success": False, "message": "您已在游戏中"}
        
        # 检查玩家数量限制
        config = Config.load_config()
        if len(self.players) >= config.game.multiplayer_g21_max_players:
            return {"success": False, "message": "游戏人数已满"}
        
        # 创建玩家状态
        player = {
            "user_id": user_id,
            "username": username,
            "bet_amount": bet_amount,
            "cards": [],
            "state": PlayerState.PLAYING,
            "points": 0,
            "lock": asyncio.Lock()
        }
        
        self.players.append(player)
        LOGGER.info(f"玩家加入 - 群组ID: {self.group_id}, 用户ID: {user_id}, 下注: {bet_amount}")
        
        return {"success": True, "message": "加入成功"}
    
    async def remove_player(self, user_id: int) -> dict:
        """
        移除玩家并退款
        
        参数:
            user_id: 用户ID
            
        返回:
            dict: {"success": bool, "refund_amount": int}
        """
        player = self.get_player(user_id)
        if not player:
            return {"success": False, "refund_amount": 0}
        
        bet_amount = player['bet_amount']
        
        # 退款（带重试）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                user = sql_get_emby(user_id)
                if user:
                    new_balance = user.iv + bet_amount
                    sql_update_emby(Emby.tg == user_id, iv=new_balance)
                    break
            except Exception as e:
                LOGGER.error(f"退款失败 - 尝试 {attempt + 1}/{max_retries}, 用户ID: {user_id}, 错误: {e}")
                if attempt == max_retries - 1:
                    LOGGER.critical(f"退款彻底失败 - 用户ID: {user_id}, 金额: {bet_amount}")
                await asyncio.sleep(1)
        
        # 从玩家列表中移除
        self.players = [p for p in self.players if p['user_id'] != user_id]
        LOGGER.info(f"玩家退出 - 群组ID: {self.group_id}, 用户ID: {user_id}, 退款: {bet_amount}")
        
        return {"success": True, "refund_amount": bet_amount}
    
    async def cleanup(self, client: Client, refund_all: bool = False):
        """
        清理游戏会话
        
        参数:
            client: Telegram 客户端
            refund_all: 是否退还所有玩家的下注金额
        """
        # 取消异步任务
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
        
        # 退款
        if refund_all:
            for player in self.players:
                try:
                    user = sql_get_emby(player['user_id'])
                    if user:
                        new_balance = user.iv + player['bet_amount']
                        sql_update_emby(Emby.tg == player['user_id'], iv=new_balance)
                except Exception as e:
                    LOGGER.error(f"清理时退款失败 - 用户ID: {player['user_id']}, 错误: {e}")
        
        # 删除消息
        try:
            if self.lobby_message_id:
                await client.delete_messages(self.group_id, self.lobby_message_id)
        except Exception as e:
            LOGGER.warning(f"删除筹备阶段消息失败: {e}")
        
        try:
            if self.scoreboard_message_id:
                await client.delete_messages(self.group_id, self.scoreboard_message_id)
        except Exception as e:
            LOGGER.warning(f"删除看板消息失败: {e}")
        
        # 清理玩家操作锁
        for player in self.players:
            lock_key = (self.group_id, player['user_id'])
            if lock_key in player_operation_locks:
                del player_operation_locks[lock_key]
        
        # 从全局字典中移除
        if self.group_id in active_multiplayer_g21_games:
            del active_multiplayer_g21_games[self.group_id]
        
        LOGGER.info(f"清理游戏会话 - 群组ID: {self.group_id}, 退款: {refund_all}")
    
    async def start_action_phase(self, client: Client):
        """
        开始操作阶段
        
        参数:
            client: Telegram 客户端
        """
        # 取消筹备阶段倒计时
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        
        # 删除筹备阶段消息
        try:
            if self.lobby_message_id:
                await client.delete_messages(self.group_id, self.lobby_message_id)
        except Exception as e:
            LOGGER.warning(f"删除筹备阶段消息失败: {e}")
        
        # 更新阶段
        self.phase = GamePhase.ACTION
        
        # 创建管理器
        action_controller = ActionPhaseController(self)
        
        # 发牌
        await action_controller.deal_initial_cards()
        
        # 创建看板消息
        await action_controller.create_scoreboard(client, self.group_id)
        
        # 启动批量更新循环
        self.update_task = asyncio.create_task(
            action_controller.start_batch_update_loop(client)
        )
        
        # 启动操作阶段倒计时
        async def action_countdown():
            self.action_remaining = self.action_timeout
            
            while self.action_remaining > 0 and self.phase == GamePhase.ACTION:
                await asyncio.sleep(1)
                self.action_remaining -= 1
            
            # 倒计时结束，检查是否还在操作阶段
            if self.phase == GamePhase.ACTION:
                # 将所有仍在操作的玩家设置为停牌
                for player in self.players:
                    if player['state'] == PlayerState.PLAYING:
                        player['state'] = PlayerState.STAND
                
                # 开始结算
                await self.start_resolution_phase(client)
        
        self.countdown_task = asyncio.create_task(action_countdown())
        
        LOGGER.info(f"开始操作阶段 - 群组ID: {self.group_id}")
    
    async def start_resolution_phase(self, client: Client):
        """
        开始结算阶段
        
        参数:
            client: Telegram 客户端
        """
        # 取消操作阶段倒计时
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        
        # 停止批量更新循环
        if self.update_task and not self.update_task.done():
            self.update_task.cancel()
        
        # 更新阶段
        self.phase = GamePhase.RESOLUTION
        
        # 创建结算管理器
        resolution_manager = ResolutionManager(self)
        
        # 庄家抽牌
        await resolution_manager.dealer_draw_cards()
        
        # 更新看板显示庄家所有牌
        try:
            message_text = ScoreboardRenderer.render_scoreboard(
                self.dealer_cards,
                self.players,
                0,
                hide_dealer_second=False
            )
            await client.edit_message_text(
                chat_id=self.group_id,
                message_id=self.scoreboard_message_id,
                text=message_text + "\n\n⏳ 正在结算..."
            )
        except Exception as e:
            LOGGER.error(f"更新看板失败: {e}")
        
        # 结算所有玩家
        results = await resolution_manager.settle_all_players()
        
        # 发送结算消息
        await resolution_manager.send_settlement_message(client, self.group_id, results)
        
        # 清理会话
        await self.cleanup(client, refund_all=False)
        
        LOGGER.info(f"结算完成 - 群组ID: {self.group_id}")


# ==================== 筹备阶段管理器 ====================

class LobbyManager:
    """筹备阶段管理器"""
    
    def __init__(self, session: MultiplayerG21Session):
        """
        初始化筹备阶段管理器
        
        参数:
            session: 游戏会话对象
        """
        self.session = session
    
    async def create_lobby_panel(self, client: Client, group_id: int) -> int:
        """
        创建筹备阶段消息面板
        
        参数:
            client: Telegram 客户端
            group_id: 群组ID
            
        返回:
            int: 消息ID
        """
        message_text = ScoreboardRenderer.render_lobby(
            self.session.players,
            self.session.lobby_remaining
        )
        
        # 创建"下车退款"按钮
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚪 下车退款", callback_data=f"mpg21_quit_{group_id}")]
        ])
        
        message = await client.send_message(
            chat_id=group_id,
            text=message_text,
            reply_markup=keyboard
        )
        
        self.session.lobby_message_id = message.id
        return message.id
    
    async def update_lobby_panel(self, client: Client):
        """
        更新筹备阶段消息面板
        
        参数:
            client: Telegram 客户端
        """
        if not self.session.lobby_message_id:
            return
        
        message_text = ScoreboardRenderer.render_lobby(
            self.session.players,
            self.session.lobby_remaining
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚪 下车退款", callback_data=f"mpg21_quit_{self.session.group_id}")]
        ])
        
        try:
            await client.edit_message_text(
                chat_id=self.session.group_id,
                message_id=self.session.lobby_message_id,
                text=message_text,
                reply_markup=keyboard
            )
        except FloodWait as e:
            LOGGER.warning(f"触发限流，等待 {e.value} 秒")
            await asyncio.sleep(e.value)
        except Exception as e:
            LOGGER.error(f"更新筹备阶段消息失败: {e}")
    
    async def start_countdown(self, client: Client, timeout_seconds: int):
        """
        启动倒计时
        
        参数:
            client: Telegram 客户端
            timeout_seconds: 超时秒数
        """
        self.session.lobby_remaining = timeout_seconds
        
        while self.session.lobby_remaining > 0 and self.session.phase == GamePhase.LOBBY:
            await asyncio.sleep(1)
            self.session.lobby_remaining -= 1
            
            # 每5秒更新一次消息
            if self.session.lobby_remaining % 5 == 0:
                await self.update_lobby_panel(client)
        
        # 倒计时结束，检查是否还在筹备阶段
        if self.session.phase == GamePhase.LOBBY:
            if len(self.session.players) > 0:
                # 有玩家，开始游戏
                await self.session.start_action_phase(client)
            else:
                # 没有玩家，清理会话
                await self.session.cleanup(client, refund_all=False)


# ==================== 操作阶段控制器 ====================

class ActionPhaseController:
    """操作阶段控制器"""
    
    def __init__(self, session: MultiplayerG21Session):
        """
        初始化操作阶段控制器
        
        参数:
            session: 游戏会话对象
        """
        self.session = session
    
    async def deal_initial_cards(self):
        """发初始手牌"""
        # 创建牌堆
        self.session.deck = G21Logic.create_deck()
        
        # 给庄家发两张牌
        self.session.dealer_cards = [
            G21Logic.deal_card(self.session.deck),
            G21Logic.deal_card(self.session.deck)
        ]
        
        # 给每个玩家发两张牌
        for player in self.session.players:
            player['cards'] = [
                G21Logic.deal_card(self.session.deck),
                G21Logic.deal_card(self.session.deck)
            ]
            player['points'] = G21Logic.calculate_points(player['cards'])
            
            # 检查起手 Blackjack
            if player['points'] == 21 and len(player['cards']) == 2:
                player['state'] = PlayerState.BLACKJACK
        
        LOGGER.info(f"发牌完成 - 群组ID: {self.session.group_id}, 玩家数: {len(self.session.players)}")
    
    async def handle_hit(self, user_id: int) -> dict:
        """
        处理要牌操作
        
        参数:
            user_id: 用户ID
            
        返回:
            dict: {"success": bool, "message": str, "card": str, "points": int, "state": str}
        """
        player = self.session.get_player(user_id)
        if not player:
            return {"success": False, "message": "您不在游戏中"}
        
        # 使用玩家操作锁
        async with player['lock']:
            # 验证玩家状态
            if player['state'] != PlayerState.PLAYING:
                return {"success": False, "message": "您已完成操作"}
            
            # 发牌
            new_card = G21Logic.deal_card(self.session.deck)
            if not new_card:
                return {"success": False, "message": "牌堆已空"}
            
            player['cards'].append(new_card)
            player['points'] = G21Logic.calculate_points(player['cards'])
            
            # 检查爆牌
            if player['points'] > 21:
                player['state'] = PlayerState.BUST
                message = f"💥 爆牌！抽到 {new_card}，当前点数：{player['points']}"
            # 检查五小龙
            elif len(player['cards']) == 5 and player['points'] <= 21:
                player['state'] = PlayerState.FIVE_DRAGON
                message = f"🐉 五小龙！抽到 {new_card}，当前点数：{player['points']}"
            else:
                message = f"🎴 抽到 {new_card}，当前点数：{player['points']}"
            
            LOGGER.info(
                f"玩家要牌 - 群组ID: {self.session.group_id}, 用户ID: {user_id}, "
                f"牌: {new_card}, 点数: {player['points']}, 状态: {player['state']}"
            )
            
            return {
                "success": True,
                "message": message,
                "card": new_card,
                "points": player['points'],
                "state": player['state']
            }
    
    async def handle_stand(self, user_id: int) -> dict:
        """
        处理停牌操作
        
        参数:
            user_id: 用户ID
            
        返回:
            dict: {"success": bool, "message": str}
        """
        player = self.session.get_player(user_id)
        if not player:
            return {"success": False, "message": "您不在游戏中"}
        
        # 使用玩家操作锁
        async with player['lock']:
            # 验证玩家状态
            if player['state'] != PlayerState.PLAYING:
                return {"success": False, "message": "您已完成操作"}
            
            # 设置为停牌状态
            player['state'] = PlayerState.STAND
            
            LOGGER.info(
                f"玩家停牌 - 群组ID: {self.session.group_id}, 用户ID: {user_id}, "
                f"点数: {player['points']}"
            )
            
            return {
                "success": True,
                "message": f"🛑 停牌成功，当前点数：{player['points']}"
            }
    
    async def create_scoreboard(self, client: Client, group_id: int) -> int:
        """
        创建看板消息
        
        参数:
            client: Telegram 客户端
            group_id: 群组ID
            
        返回:
            int: 消息ID
        """
        message_text = ScoreboardRenderer.render_scoreboard(
            self.session.dealer_cards,
            self.session.players,
            self.session.action_remaining,
            hide_dealer_second=True
        )
        
        # 创建操作按钮
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎴 要牌", callback_data=f"mpg21_hit_{group_id}"),
                InlineKeyboardButton("🛑 停牌", callback_data=f"mpg21_stand_{group_id}")
            ]
        ])
        
        message = await client.send_message(
            chat_id=group_id,
            text=message_text,
            reply_markup=keyboard
        )
        
        self.session.scoreboard_message_id = message.id
        return message.id
    
    async def update_scoreboard(self, client: Client):
        """
        更新看板消息
        
        参数:
            client: Telegram 客户端
        """
        if not self.session.scoreboard_message_id:
            return
        
        message_text = ScoreboardRenderer.render_scoreboard(
            self.session.dealer_cards,
            self.session.players,
            self.session.action_remaining,
            hide_dealer_second=True
        )
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🎴 要牌", callback_data=f"mpg21_hit_{self.session.group_id}"),
                InlineKeyboardButton("🛑 停牌", callback_data=f"mpg21_stand_{self.session.group_id}")
            ]
        ])
        
        try:
            await client.edit_message_text(
                chat_id=self.session.group_id,
                message_id=self.session.scoreboard_message_id,
                text=message_text,
                reply_markup=keyboard
            )
        except FloodWait as e:
            LOGGER.warning(f"触发限流，等待 {e.value} 秒")
            await asyncio.sleep(e.value)
        except Exception as e:
            LOGGER.error(f"更新看板失败: {e}")
    
    async def start_batch_update_loop(self, client: Client):
        """
        启动批量更新循环
        
        参数:
            client: Telegram 客户端
        """
        update_interval = 4  # 每4秒更新一次
        
        while self.session.phase == GamePhase.ACTION:
            await asyncio.sleep(update_interval)
            
            if self.session.phase != GamePhase.ACTION:
                break
            
            await self.update_scoreboard(client)
    
    def check_all_players_done(self) -> bool:
        """
        检查是否所有玩家都已完成操作
        
        返回:
            bool: 是否所有玩家都已完成
        """
        for player in self.session.players:
            if player['state'] == PlayerState.PLAYING:
                return False
        return True


# ==================== 结算管理器 ====================

class ResolutionManager:
    """结算管理器"""
    
    def __init__(self, session: MultiplayerG21Session):
        """
        初始化结算管理器
        
        参数:
            session: 游戏会话对象
        """
        self.session = session
    
    async def dealer_draw_cards(self):
        """庄家自动抽牌"""
        self.session.dealer_cards = G21Logic.dealer_auto_draw(
            self.session.dealer_cards,
            self.session.deck
        )
        dealer_points = G21Logic.calculate_points(self.session.dealer_cards)
        LOGGER.info(f"庄家抽牌完成 - 群组ID: {self.session.group_id}, 点数: {dealer_points}")
    
    async def settle_single_player(self, player: dict) -> dict:
        """
        结算单个玩家
        
        参数:
            player: 玩家状态字典
            
        返回:
            dict: 结算结果
        """
        player_points = player['points']
        dealer_points = G21Logic.calculate_points(self.session.dealer_cards)
        bet_amount = player['bet_amount']
        user_id = player['user_id']
        
        # 判定胜负
        if player['state'] == PlayerState.BUST:
            # 玩家爆牌，庄家赢
            result = "LOSE"
            payout = 0
            win_type = None
        elif player['state'] == PlayerState.BLACKJACK and dealer_points != 21:
            # 玩家 Blackjack，庄家不是
            result = "WIN"
            payout = int(bet_amount * 1.5)
            win_type = "BLACKJACK"
        elif player['state'] == PlayerState.FIVE_DRAGON:
            # 玩家五小龙
            result = "WIN"
            payout = bet_amount * 2
            win_type = "FIVE_DRAGON"
        elif dealer_points > 21:
            # 庄家爆牌，玩家赢
            result = "WIN"
            payout = bet_amount
            win_type = "NORMAL"
        elif player_points > dealer_points:
            # 玩家点数大
            result = "WIN"
            payout = bet_amount
            win_type = "NORMAL"
        elif player_points < dealer_points:
            # 庄家点数大
            result = "LOSE"
            payout = 0
            win_type = None
        else:
            # 平局
            result = "DRAW"
            payout = 0
            win_type = None
        
        # 更新金币（带重试）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                user = sql_get_emby(user_id)
                if user:
                    if result == "WIN":
                        # 赢：退还本金 + 赔付
                        new_balance = user.iv + bet_amount + payout
                        sql_update_emby(Emby.tg == user_id, iv=new_balance)
                    elif result == "DRAW":
                        # 平局：退还本金
                        new_balance = user.iv + bet_amount
                        sql_update_emby(Emby.tg == user_id, iv=new_balance)
                    # 输：不退还本金
                    break
            except Exception as e:
                LOGGER.error(f"结算失败 - 尝试 {attempt + 1}/{max_retries}, 用户ID: {user_id}, 错误: {e}")
                if attempt == max_retries - 1:
                    LOGGER.critical(f"结算彻底失败 - 用户ID: {user_id}, 下注: {bet_amount}, 赔付: {payout}")
                await asyncio.sleep(1)
        
        return {
            "user_id": user_id,
            "username": player['username'],
            "bet_amount": bet_amount,
            "result": result,
            "win_type": win_type,
            "payout": payout,
            "player_points": player_points,
            "dealer_points": dealer_points
        }
    
    async def settle_all_players(self) -> List[dict]:
        """
        结算所有玩家
        
        返回:
            List[dict]: 结算结果列表
        """
        results = []
        
        for player in self.session.players:
            result = await self.settle_single_player(player)
            results.append(result)
        
        LOGGER.info(f"结算完成 - 群组ID: {self.session.group_id}, 玩家数: {len(results)}")
        return results
    
    async def send_settlement_message(self, client: Client, group_id: int, results: List[dict]):
        """
        发送结算消息
        
        参数:
            client: Telegram 客户端
            group_id: 群组ID
            results: 结算结果列表
        """
        message_text = ScoreboardRenderer.render_settlement(results, self.session.dealer_cards)
        
        try:
            message = await client.send_message(
                chat_id=group_id,
                text=message_text
            )
            
            # 180秒后自动删除
            async def delete_after_delay():
                await asyncio.sleep(180)
                try:
                    await client.delete_messages(group_id, message.id)
                except Exception as e:
                    LOGGER.warning(f"删除结算消息失败: {e}")
            
            asyncio.create_task(delete_after_delay())
            
        except Exception as e:
            LOGGER.error(f"发送结算消息失败: {e}")


# ==================== 指令处理器 ====================

@bot.on_message(filters.command('g21', prefixes=prefixes) & filters.group)
async def handle_multiplayer_g21_command(client: Client, message: Message):
    """
    处理 /g21 指令（多人模式）
    
    参数:
        client: Telegram 客户端
        message: 消息对象
    """
    # 检查游戏总开关
    config = Config.load_config()
    if not config.game.multiplayer_g21_open:
        try:
            await message.delete()
        except:
            pass
        return
    
    # 立即删除指令消息
    try:
        await message.delete()
    except Exception as e:
        LOGGER.warning(f"删除指令消息失败: {e}")
    
    user_id = message.from_user.id
    username = message.from_user.first_name or f"用户{user_id}"
    group_id = message.chat.id
    command_text = message.text or ""
    
    try:
        # 1. 查询用户信息
        user = sql_get_emby(user_id)
        if not user:
            error_msg = await message.reply_text("❌ 您还未在系统中初始化，请先私信我激活")
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        user_balance = user.iv
        
        # 2. 解析指令
        parse_result = CommandParser.parse_g21_command(command_text, user_balance)
        if not parse_result['success']:
            error_msg = await message.reply_text(f"❌ {parse_result['error_message']}")
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        bet_amount = parse_result['bet_amount']
        
        # 3. 验证下注金额范围
        if bet_amount < config.game.multiplayer_g21_min_bet:
            error_msg = await message.reply_text(
                f"❌ 下注金额不能低于 {config.game.multiplayer_g21_min_bet} 金币"
            )
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        if bet_amount > config.game.multiplayer_g21_max_bet:
            error_msg = await message.reply_text(
                f"❌ 下注金额不能超过 {config.game.multiplayer_g21_max_bet} 金币"
            )
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        # 4. 检查余额
        if user_balance < bet_amount:
            error_msg = await message.reply_text(
                f"❌ 余额不足！当前余额：{user_balance} 金币"
            )
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        # 5. 获取或创建游戏会话
        if group_id not in active_multiplayer_g21_games:
            # 创建新会话
            session = MultiplayerG21Session(group_id)
            active_multiplayer_g21_games[group_id] = session
            
            # 创建筹备阶段管理器
            lobby_manager = LobbyManager(session)
            await lobby_manager.create_lobby_panel(client, group_id)
            
            # 启动倒计时
            session.countdown_task = asyncio.create_task(
                lobby_manager.start_countdown(client, session.lobby_timeout)
            )
        else:
            session = active_multiplayer_g21_games[group_id]
            lobby_manager = LobbyManager(session)
        
        # 6. 扣除金币
        try:
            new_balance = user.iv - bet_amount
            sql_update_emby(Emby.tg == user_id, iv=new_balance)
        except Exception as e:
            LOGGER.error(f"扣除金币失败 - 用户ID: {user_id}, 错误: {e}")
            error_msg = await message.reply_text("❌ 系统错误，请稍后再试")
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        # 7. 添加玩家
        result = await session.add_player(user_id, username, bet_amount)
        if not result['success']:
            # 添加失败，退还金币
            try:
                refund_balance = user.iv + bet_amount
                sql_update_emby(Emby.tg == user_id, iv=refund_balance)
            except:
                pass
            
            error_msg = await message.reply_text(f"❌ {result['message']}")
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
            return
        
        # 8. 更新筹备阶段消息
        await lobby_manager.update_lobby_panel(client)
        
        # 9. 检查是否达到最大玩家数
        if len(session.players) >= config.game.multiplayer_g21_max_players:
            # 立即开始游戏
            await session.start_action_phase(client)
        
        # 10. 发送私信通知
        try:
            await client.send_message(
                user_id,
                f"✅ 您已成功加入多人21点游戏\n"
                f"💰 下注金额：{bet_amount} 金币\n"
                f"💳 当前余额：{new_balance} 金币"
            )
        except:
            pass
        
        LOGGER.info(
            f"玩家加入多人游戏 - 群组ID: {group_id}, 用户ID: {user_id}, "
            f"下注: {bet_amount}, 当前玩家数: {len(session.players)}"
        )
        
    except Exception as e:
        LOGGER.error(f"处理多人 /g21 指令失败: {e}")
        try:
            error_msg = await message.reply_text("❌ 系统错误，请稍后重试")
            asyncio.create_task(delete_message_after_delay(client, group_id, error_msg.id, 60))
        except:
            pass


# ==================== 回调处理器 ====================

@bot.on_callback_query(filters.regex(r"^mpg21_quit_"))
async def handle_lobby_quit_callback(client: Client, call: CallbackQuery):
    """
    处理"下车退款"按钮
    
    参数:
        client: Telegram 客户端
        call: 回调查询对象
    """
    try:
        # 解析回调数据
        parts = call.data.split('_')
        if len(parts) < 3:
            await call.answer("❌ 无效的回调数据", show_alert=True)
            return
        
        group_id = int(parts[2])
        user_id = call.from_user.id
        
        # 检查游戏是否存在
        if group_id not in active_multiplayer_g21_games:
            await call.answer("❌ 游戏不存在", show_alert=True)
            return
        
        session = active_multiplayer_g21_games[group_id]
        
        # 检查游戏阶段
        if session.phase != GamePhase.LOBBY:
            await call.answer("❌ 游戏已开始，无法退出", show_alert=True)
            return
        
        # 检查玩家是否在游戏中
        if not session.is_player_in_game(user_id):
            await call.answer("❌ 您不在游戏中", show_alert=False)
            return
        
        # 移除玩家并退款
        result = await session.remove_player(user_id)
        if result['success']:
            await call.answer(
                f"✅ 已退出游戏，退还 {result['refund_amount']} 金币",
                show_alert=False
            )
            
            # 更新筹备阶段消息
            lobby_manager = LobbyManager(session)
            await lobby_manager.update_lobby_panel(client)
            
            # 如果所有玩家都退出，清理会话
            if len(session.players) == 0:
                await session.cleanup(client, refund_all=False)
        else:
            await call.answer("❌ 退出失败", show_alert=True)
        
    except Exception as e:
        LOGGER.error(f"处理退出回调失败: {e}")
        try:
            await call.answer("❌ 处理请求时出错", show_alert=True)
        except:
            pass


@bot.on_callback_query(filters.regex(r"^mpg21_hit_"))
async def handle_hit_callback(client: Client, call: CallbackQuery):
    """
    处理"要牌"按钮
    
    参数:
        client: Telegram 客户端
        call: 回调查询对象
    """
    try:
        # 解析回调数据
        parts = call.data.split('_')
        if len(parts) < 3:
            await call.answer("❌ 无效的回调数据", show_alert=True)
            return
        
        group_id = int(parts[2])
        user_id = call.from_user.id
        
        # 检查游戏是否存在
        if group_id not in active_multiplayer_g21_games:
            await call.answer("❌ 游戏不存在", show_alert=True)
            return
        
        session = active_multiplayer_g21_games[group_id]
        
        # 检查游戏阶段
        if session.phase != GamePhase.ACTION:
            await call.answer("❌ 当前不在操作阶段", show_alert=True)
            return
        
        # 检查玩家是否在游戏中
        if not session.is_player_in_game(user_id):
            await call.answer("❌ 您不在游戏中", show_alert=False)
            return
        
        # 处理要牌
        action_controller = ActionPhaseController(session)
        result = await action_controller.handle_hit(user_id)
        
        if result['success']:
            await call.answer(result['message'], show_alert=False)
            
            # 检查是否所有玩家都完成操作
            if action_controller.check_all_players_done():
                await session.start_resolution_phase(client)
        else:
            await call.answer(result['message'], show_alert=False)
        
    except Exception as e:
        LOGGER.error(f"处理要牌回调失败: {e}")
        try:
            await call.answer("❌ 处理请求时出错", show_alert=True)
        except:
            pass


@bot.on_callback_query(filters.regex(r"^mpg21_stand_"))
async def handle_stand_callback(client: Client, call: CallbackQuery):
    """
    处理"停牌"按钮
    
    参数:
        client: Telegram 客户端
        call: 回调查询对象
    """
    try:
        # 解析回调数据
        parts = call.data.split('_')
        if len(parts) < 3:
            await call.answer("❌ 无效的回调数据", show_alert=True)
            return
        
        group_id = int(parts[2])
        user_id = call.from_user.id
        
        # 检查游戏是否存在
        if group_id not in active_multiplayer_g21_games:
            await call.answer("❌ 游戏不存在", show_alert=True)
            return
        
        session = active_multiplayer_g21_games[group_id]
        
        # 检查游戏阶段
        if session.phase != GamePhase.ACTION:
            await call.answer("❌ 当前不在操作阶段", show_alert=True)
            return
        
        # 检查玩家是否在游戏中
        if not session.is_player_in_game(user_id):
            await call.answer("❌ 您不在游戏中", show_alert=False)
            return
        
        # 处理停牌
        action_controller = ActionPhaseController(session)
        result = await action_controller.handle_stand(user_id)
        
        if result['success']:
            await call.answer(result['message'], show_alert=False)
            
            # 检查是否所有玩家都完成操作
            if action_controller.check_all_players_done():
                await session.start_resolution_phase(client)
        else:
            await call.answer(result['message'], show_alert=False)
        
    except Exception as e:
        LOGGER.error(f"处理停牌回调失败: {e}")
        try:
            await call.answer("❌ 处理请求时出错", show_alert=True)
        except:
            pass


# ==================== 辅助函数 ====================

async def delete_message_after_delay(client: Client, chat_id: int, message_id: int, delay: int):
    """
    延迟删除消息
    
    参数:
        client: Telegram 客户端
        chat_id: 聊天ID
        message_id: 消息ID
        delay: 延迟秒数
    """
    await asyncio.sleep(delay)
    try:
        await client.delete_messages(chat_id, message_id)
    except Exception as e:
        LOGGER.warning(f"删除消息失败: {e}")


async def monitor_session_timeout():
    """
    监控会话超时（5分钟强制清理）
    """
    while True:
        await asyncio.sleep(60)  # 每分钟检查一次
        
        current_time = time.time()
        expired_sessions = []
        
        for group_id, session in active_multiplayer_g21_games.items():
            if current_time - session.created_at > 300:  # 5分钟
                expired_sessions.append(group_id)
        
        for group_id in expired_sessions:
            LOGGER.warning(f"清理过期会话 - 群组ID: {group_id}")
            session = active_multiplayer_g21_games[group_id]
            # 注意：这里需要 client 对象，实际部署时需要从全局获取
            # await session.cleanup(client, refund_all=True)
