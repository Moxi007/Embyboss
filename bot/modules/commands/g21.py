"""
21点游戏模块

支持1-20人同时参与的21点游戏。
由玩家通过 /startg21 发起并担任庄家，其他玩家通过 /g21 参与。
平局判定为庄家胜出，所有筹码的输赢直接在庄家与玩家间结算。
玩家退出或庄家强制解散均会面临金币扣除惩罚。
"""

import asyncio
import random
import time
from typing import Dict, List, Optional
from pyrogram import Client, filters
from pyrogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from pyrogram.errors import FloodWait, MessageNotModified

# 导入 bot 原有变量和配置
from bot import bot, prefixes, sakura_b, game, LOGGER
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby


# ==================== 21点游戏核心逻辑类 ====================

class G21Logic:
    """21点游戏核心逻辑类"""
    
    SUITS = ['♠', '♥', '♣', '♦']
    RANKS = ['A', '2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K']

    @staticmethod
    def create_deck() -> List[str]:
        deck = [f"{suit}{rank}" for suit in G21Logic.SUITS for rank in G21Logic.RANKS]
        for i in range(len(deck) - 1, 0, -1):
            j = random.randint(0, i)
            deck[i], deck[j] = deck[j], deck[i]
        return deck
    
    @staticmethod
    def deal_card(deck: List[str]) -> str:
        if deck: return deck.pop()
        return None

    @staticmethod
    def calculate_points(cards: List[str]) -> int:
        total = 0
        ace_count = 0
        for card in cards:
            rank = card[1:]
            if rank == 'A':
                ace_count += 1
                total += 11
            elif rank in ['J', 'Q', 'K']:
                total += 10
            else:
                total += int(rank)
        
        while total > 21 and ace_count > 0:
            total -= 10
            ace_count -= 1
        return total

    @staticmethod
    def dealer_auto_draw(dealer_cards: List[str], deck: List[str]) -> List[str]:
        while True:
            points = G21Logic.calculate_points(dealer_cards)
            if points >= 17 or points > 21 or len(dealer_cards) >= 5:
                break
            if deck:
                card = G21Logic.deal_card(deck)
                if card:
                    dealer_cards.append(card)
                else:
                    break
            else:
                break
        return dealer_cards


def format_card(card: str, hidden: bool = False) -> str:
    if hidden: return "🂠"
    return card


def format_hand(cards: List[str], hide_second: bool = False) -> str:
    result = []
    for i, card in enumerate(cards):
        if i == 1 and hide_second:
            result.append(format_card(card, hidden=True))
        else:
            result.append(format_card(card))
    return " ".join(result)


# ==================== 全局状态与常量 ====================

active_g21_games: Dict[int, 'G21Session'] = {}
_monitor_task_started = False

class GamePhase:
    LOBBY = "LOBBY"
    DEALER_ACTION = "DEALER_ACTION"  # 新增：庄家操作阶段
    PLAYER_ACTION = "PLAYER_ACTION"  # 重命名：原ACTION改为PLAYER_ACTION
    RESOLUTION = "RESOLUTION"

class PlayerState:
    PLAYING = "PLAYING"
    STAND = "STAND"
    BUST = "BUST"
    BLACKJACK = "BLACKJACK"
    FIVE_DRAGON = "FIVE_DRAGON"


# ==================== 解析器与看板 ====================

class CommandParser:
    @staticmethod
    def parse_g21_command(command_text: str, user_balance: int) -> dict:
        parts = command_text.strip().split()
        if len(parts) < 2:
            return {"success": False, "bet_amount": 0, "error_message": "指令格式错误，正确格式：/g21 [金额] 或 /g21 all"}
        
        bet_str = parts[1].lower()
        if bet_str == "all":
            if user_balance <= 0:
                return {"success": False, "bet_amount": 0, "error_message": "余额不足，无法下注"}
            return {"success": True, "bet_amount": user_balance, "error_message": ""}
        
        try:
            bet_amount = int(bet_str)
            if bet_amount <= 0:
                return {"success": False, "bet_amount": 0, "error_message": "下注金额必须为正整数"}
            return {"success": True, "bet_amount": bet_amount, "error_message": ""}
        except ValueError:
            return {"success": False, "bet_amount": 0, "error_message": "金额格式错误，请输入数字或 'all'"}


class ScoreboardRenderer:
    @staticmethod
    def format_user_link(user_id: int, username: str) -> str:
        """生成可点击的用户链接"""
        return f"[{username}](tg://user?id={user_id})"
    
    @staticmethod
    def render_lobby(dealer_user_id: int, dealer_name: str, players: List[dict], countdown: int) -> str:
        dealer_link = ScoreboardRenderer.format_user_link(dealer_user_id, dealer_name)
        lines = [
            "🎰 **21点游戏 - 筹备阶段**", "",
            f"🎩 **本局庄家：** {dealer_link}",
            f"⏱ 倒计时：**{countdown}** 秒",
            f"👥 当前玩家数：**{len(players)}**/20", "",
            "📋 **玩家列表：**"
        ]
        for i, player in enumerate(players, 1):
            user_link = ScoreboardRenderer.format_user_link(player['user_id'], player['username'])
            lines.append(f"{i}. {user_link} - 下注 **{player['bet_amount']}** {sakura_b}")
        
        if len(players) == 0:
            lines.append("- 暂无玩家上车 -")
            
        lines.append("")
        lines.append("💡 发送 `/g21 [金额]` 参与对局")
        lines.append(f"💡 退出游戏将扣除惩罚 (⚠️ 玩家违约扣 20%，庄家违约扣 100 {sakura_b})")
        return "\n".join(lines)
    
    @staticmethod
    def render_dealer_action_scoreboard(dealer_user_id: int, dealer_name: str, dealer_cards: List[str], 
                                        players: List[dict], countdown: int) -> str:
        """渲染庄家操作阶段的看板"""
        dealer_link = ScoreboardRenderer.format_user_link(dealer_user_id, dealer_name)
        dealer_points = G21Logic.calculate_points([dealer_cards[0]])  # 只显示明牌点数
        
        lines = [
            "🎰 **多人21点游戏 - 庄家操作阶段**", "",
            f"⏱ 剩余时间：**{countdown}** 秒", "",
            f"🎩 **庄家 ({dealer_link})**",
            f"明牌：{dealer_cards[0]} (点数：{dealer_points})",
            f"暗牌：🂠", "",
            "👥 **等待庄家操作中...**", "",
            "📋 **玩家列表：**"
        ]
        
        for i, player in enumerate(players, 1):
            user_link = ScoreboardRenderer.format_user_link(player['user_id'], player['username'])
            lines.append(f"{i}. {user_link} - 下注 **{player['bet_amount']}** {sakura_b}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_player_action_scoreboard(dealer_user_id: int, dealer_name: str, dealer_cards: List[str], players: List[dict], 
                         countdown: int, hide_dealer_second: bool = True) -> str:
        dealer_link = ScoreboardRenderer.format_user_link(dealer_user_id, dealer_name)
        lines = [
            "🎰 **21点游戏 - 玩家操作阶段**", "",
            f"⏱ 剩余时间：**{countdown}** 秒", "",
            f"🎩 **庄家 ({dealer_link}) 手牌：**"
        ]
        
        dealer_hand = format_hand(dealer_cards, hide_second=hide_dealer_second)
        if hide_dealer_second:
            dealer_points = G21Logic.calculate_points([dealer_cards[0]])
            lines.append(f"{dealer_hand} (明牌点数：{dealer_points})")
        else:
            dealer_points = G21Logic.calculate_points(dealer_cards)
            lines.append(f"{dealer_hand} (点数：{dealer_points})")
        
        lines.append("")
        lines.append("👥 **玩家状态：**")
        
        for i, player in enumerate(players, 1):
            player_hand = format_hand(player['cards'])
            points = player['points']
            state = player['state']
            
            state_icon = {
                PlayerState.PLAYING: "🎮", PlayerState.STAND: "🛑",
                PlayerState.BUST: "💥", PlayerState.BLACKJACK: "⭐", PlayerState.FIVE_DRAGON: "🐉"
            }.get(state, "❓")
            
            state_text = {
                PlayerState.PLAYING: "操作中", PlayerState.STAND: "已停牌",
                PlayerState.BUST: "已爆牌", PlayerState.BLACKJACK: "Blackjack", PlayerState.FIVE_DRAGON: "五小龙"
            }.get(state, "未知")
            
            user_link = ScoreboardRenderer.format_user_link(player['user_id'], player['username'])
            lines.append(f"{i}. {state_icon} {user_link} (下注 {player['bet_amount']} {sakura_b})")
            lines.append(f"   手牌：{player_hand} | 点数：**{points}** | {state_text}")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_settlement(dealer_user_id: int, dealer_name: str, dealer_net_profit: int, results: List[dict], dealer_cards: List[str]) -> str:
        dealer_hand = format_hand(dealer_cards)
        dealer_points = G21Logic.calculate_points(dealer_cards)
        
        profit_str = f"+{dealer_net_profit}" if dealer_net_profit > 0 else str(dealer_net_profit)
        
        # 生成庄家的可点击链接
        dealer_link = ScoreboardRenderer.format_user_link(dealer_user_id, dealer_name)
        
        lines = [
            "🎰 **21点游戏 - 结算**", "",
            f"🎩 **庄家 ({dealer_link}) 最终手牌：**",
            f"{dealer_hand} (点数：{dealer_points})", 
            f"💰 **庄家本局净收益：** **{profit_str}** {sakura_b}", "",
            "📊 **玩家结算：**"
        ]
        
        for i, result in enumerate(results, 1):
            username = result['username']
            bet_amount = result['bet_amount']
            game_result = result['result']
            payout = result['payout']
            player_points = result['player_points']
            
            if game_result == "WIN":
                icon = "🎉"
                result_text = "获胜"
                if result.get('win_type') == "BLACKJACK": result_text += " (Blackjack)"
                elif result.get('win_type') == "FIVE_DRAGON": result_text += " (五小龙)"
                coin_change = f"+{payout}" 
            else:
                icon = "😢"
                result_text = "失败 (平局算庄赢)" if result.get('win_type') == "TIE_LOSS" else "失败"
                coin_change = f"-{bet_amount}"
            
            user_link = ScoreboardRenderer.format_user_link(result['user_id'], username)
            lines.append(f"{i}. {icon} {user_link} - {result_text} (点数：{player_points}) | 变动：**{coin_change}**")
        
        lines.append("")
        lines.append("💡 本消息将在 180 秒后自动删除")
        return "\n".join(lines)


# ==================== 游戏会话管理类 ====================

class G21Session:
    def __init__(self, group_id: int, dealer_user_id: int, dealer_name: str):
        self.group_id = group_id
        self.dealer_user_id = dealer_user_id
        self.dealer_name = dealer_name
        self.dealer_net_profit = 0  
        
        self.phase = GamePhase.LOBBY
        self.players: List[dict] = []
        self.dealer_cards: List[str] = []
        self.deck: List[str] = []
        
        self.lobby_message_id: Optional[int] = None
        self.scoreboard_message_id: Optional[int] = None
        
        self.countdown_task: Optional[asyncio.Task] = None
        self.update_task: Optional[asyncio.Task] = None
        
        self.created_at = time.time()
        self.lobby_timeout = 60
        self.action_timeout = 60
        self.lobby_remaining = self.lobby_timeout
        self.action_remaining = self.action_timeout
        
        # 新增：庄家状态跟踪
        self.dealer_state = PlayerState.PLAYING
        self.dealer_action_timeout = 60
        self.dealer_remaining = self.dealer_action_timeout
    
    def get_player(self, user_id: int) -> Optional[dict]:
        for player in self.players:
            if player['user_id'] == user_id: return player
        return None
    
    def is_player_in_game(self, user_id: int) -> bool:
        return self.get_player(user_id) is not None
    
    async def add_player(self, user_id: int, username: str, bet_amount: int) -> dict:
        if self.phase != GamePhase.LOBBY:
            return {"success": False, "message": "游戏已开始，无法加入"}
        
        # 检查玩家是否已在游戏中，如果是则追加筹码
        existing_player = self.get_player(user_id)
        if existing_player:
            old_bet = existing_player['bet_amount']
            existing_player['bet_amount'] += bet_amount
            return {
                "success": True, 
                "message": "追加成功",
                "is_additional": True,
                "old_bet": old_bet,
                "additional_amount": bet_amount,
                "new_total": existing_player['bet_amount']
            }
        
        if len(self.players) >= 20:
            return {"success": False, "message": "游戏人数已满 (20人)"}
        
        player = {
            "user_id": user_id, "username": username, "bet_amount": bet_amount,
            "cards": [], "state": PlayerState.PLAYING, "points": 0,
            "lock": asyncio.Lock()
        }
        self.players.append(player)
        return {"success": True, "message": "加入成功", "is_additional": False}
    
    async def remove_player(self, user_id: int, penalty_rate: float = 0.0) -> dict:
        """移除玩家并处理退款和违约金"""
        player = self.get_player(user_id)
        if not player: return {"success": False, "refund_amount": 0, "penalty_amount": 0}
        
        bet_amount = player['bet_amount']
        penalty_amount = int(bet_amount * penalty_rate)
        refund_amount = bet_amount - penalty_amount
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                user = sql_get_emby(user_id)
                if user:
                    sql_update_emby(Emby.tg == user_id, iv=user.iv + refund_amount)
                    break
            except Exception as e:
                await asyncio.sleep(1)
        
        self.players = [p for p in self.players if p['user_id'] != user_id]
        return {
            "success": True, 
            "refund_amount": refund_amount, 
            "penalty_amount": penalty_amount
        }
    
    async def cleanup(self, client: Client, refund_all: bool = False):
        if self.countdown_task and not self.countdown_task.done(): self.countdown_task.cancel()
        if self.update_task and not self.update_task.done(): self.update_task.cancel()
        
        if refund_all:
            for player in self.players:
                try:
                    user = sql_get_emby(player['user_id'])
                    if user:
                        sql_update_emby(Emby.tg == player['user_id'], iv=user.iv + player['bet_amount'])
                except: pass
        
        try:
            if self.lobby_message_id: await client.delete_messages(self.group_id, self.lobby_message_id)
        except: pass
        try:
            if self.scoreboard_message_id: await client.delete_messages(self.group_id, self.scoreboard_message_id)
        except: pass
        
        if self.group_id in active_g21_games:
            del active_g21_games[self.group_id]
    
    async def start_dealer_action_phase(self, client: Client):
        """开始庄家操作阶段"""
        if self.countdown_task and not self.countdown_task.done(): 
            self.countdown_task.cancel()
        
        try:
            if self.lobby_message_id: 
                await client.delete_messages(self.group_id, self.lobby_message_id)
        except: pass
        
        self.phase = GamePhase.DEALER_ACTION
        action_controller = ActionPhaseController(self)
        await action_controller.deal_initial_cards()
        
        # 给庄家发送私聊消息显示完整手牌
        await action_controller.send_dealer_private_message(client)
        
        # 创建庄家操作看板
        await action_controller.create_dealer_scoreboard(client, self.group_id)
        
        # 启动庄家操作倒计时
        async def dealer_countdown():
            self.dealer_remaining = self.dealer_action_timeout
            while self.dealer_remaining > 0 and self.phase == GamePhase.DEALER_ACTION:
                await asyncio.sleep(1)
                self.dealer_remaining -= 1
            
            if self.phase == GamePhase.DEALER_ACTION:
                # 超时自动停牌
                self.dealer_state = PlayerState.STAND
                await self.start_player_action_phase(client)
        
        self.countdown_task = asyncio.create_task(dealer_countdown())
    
    async def start_player_action_phase(self, client: Client):
        """开始玩家操作阶段"""
        if self.countdown_task and not self.countdown_task.done(): 
            self.countdown_task.cancel()
        
        self.phase = GamePhase.PLAYER_ACTION
        action_controller = ActionPhaseController(self)
        
        # 创建玩家操作看板
        await action_controller.create_player_scoreboard(client, self.group_id)
        
        # 启动批量更新循环
        self.update_task = asyncio.create_task(action_controller.start_batch_update_loop(client))
        
        # 启动玩家操作倒计时
        async def player_countdown():
            self.action_remaining = self.action_timeout
            while self.action_remaining > 0 and self.phase == GamePhase.PLAYER_ACTION:
                await asyncio.sleep(1)
                self.action_remaining -= 1
            
            if self.phase == GamePhase.PLAYER_ACTION:
                for player in self.players:
                    if player['state'] == PlayerState.PLAYING:
                        player['state'] = PlayerState.STAND
                await self.start_resolution_phase(client)
        
        self.countdown_task = asyncio.create_task(player_countdown())
    
    async def start_resolution_phase(self, client: Client):
        if self.countdown_task and not self.countdown_task.done(): self.countdown_task.cancel()
        if self.update_task and not self.update_task.done(): self.update_task.cancel()
        
        self.phase = GamePhase.RESOLUTION
        resolution_manager = ResolutionManager(self)
        
        try:
            message_text = ScoreboardRenderer.render_player_action_scoreboard(
                self.dealer_user_id, self.dealer_name, self.dealer_cards, self.players, 0, hide_dealer_second=False
            )
            await client.edit_message_text(
                chat_id=self.group_id, message_id=self.scoreboard_message_id, text=message_text + "\n\n⏳ 正在结算..."
            )
        except Exception: pass
        
        results = await resolution_manager.settle_all_players()
        await resolution_manager.send_settlement_message(client, self.group_id, results)
        await self.cleanup(client, refund_all=False)


# ==================== 管理器类群 ====================

class LobbyManager:
    def __init__(self, session: G21Session):
        self.session = session
    
    async def create_lobby_panel(self, client: Client, group_id: int) -> int:
        message_text = ScoreboardRenderer.render_lobby(self.session.dealer_user_id, self.session.dealer_name, self.session.players, self.session.lobby_remaining)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚪 下车退出 / 庄家解散", callback_data=f"mpg21_quit_{group_id}")]])
        message = await client.send_message(chat_id=group_id, text=message_text, reply_markup=keyboard)
        self.session.lobby_message_id = message.id
        return message.id
    
    async def update_lobby_panel(self, client: Client):
        if not self.session.lobby_message_id: return
        message_text = ScoreboardRenderer.render_lobby(self.session.dealer_user_id, self.session.dealer_name, self.session.players, self.session.lobby_remaining)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚪 下车退出 / 庄家解散", callback_data=f"mpg21_quit_{self.session.group_id}")]])
        
        try:
            await client.edit_message_text(
                chat_id=self.session.group_id, message_id=self.session.lobby_message_id, 
                text=message_text, reply_markup=keyboard
            )
        except MessageNotModified:
            pass 
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            LOGGER.error(f"更新筹备消息失败: {e}")
    
    async def start_countdown(self, client: Client, timeout_seconds: int):
        self.session.lobby_remaining = timeout_seconds
        while self.session.lobby_remaining > 0 and self.session.phase == GamePhase.LOBBY:
            await asyncio.sleep(1)
            self.session.lobby_remaining -= 1
            if self.session.lobby_remaining % 5 == 0:
                await self.update_lobby_panel(client)
        
        if self.session.phase == GamePhase.LOBBY:
            if len(self.session.players) > 0:
                await self.session.start_dealer_action_phase(client)
            else:
                x = await client.send_message(self.session.group_id, "🈳 倒计时结束，无人上车，牌局自动解散。")
                asyncio.create_task(delete_message_after_delay(client, self.session.group_id, x.id, 20))
                await self.session.cleanup(client, refund_all=False)


class ActionPhaseController:
    def __init__(self, session: G21Session):
        self.session = session
    
    async def deal_initial_cards(self):
        self.session.deck = G21Logic.create_deck()
        self.session.dealer_cards = [G21Logic.deal_card(self.session.deck), G21Logic.deal_card(self.session.deck)]
        
        for player in self.session.players:
            player['cards'] = [G21Logic.deal_card(self.session.deck), G21Logic.deal_card(self.session.deck)]
            player['points'] = G21Logic.calculate_points(player['cards'])
            if player['points'] == 21 and len(player['cards']) == 2:
                player['state'] = PlayerState.BLACKJACK
    
    async def send_dealer_private_message(self, client: Client):
        """给庄家发送私聊消息显示完整手牌"""
        dealer_hand = format_hand(self.session.dealer_cards, hide_second=False)
        dealer_points = G21Logic.calculate_points(self.session.dealer_cards)
        
        message_text = (
            f"🎩 **您的手牌（庄家视角）**\n\n"
            f"手牌：{dealer_hand}\n"
            f"点数：**{dealer_points}**\n\n"
            f"💡 请在群组中点击按钮进行操作"
        )
        
        try:
            await client.send_message(self.session.dealer_user_id, message_text)
        except:
            pass  # 如果无法发送私聊消息，忽略错误
    
    async def handle_dealer_hit(self) -> dict:
        """处理庄家要牌"""
        if self.session.dealer_state != PlayerState.PLAYING:
            return {"success": False, "message": "您已完成操作"}
        
        new_card = G21Logic.deal_card(self.session.deck)
        if not new_card:
            return {"success": False, "message": "牌堆已空"}
        
        self.session.dealer_cards.append(new_card)
        dealer_points = G21Logic.calculate_points(self.session.dealer_cards)
        
        if dealer_points > 21:
            self.session.dealer_state = PlayerState.BUST
            message = f"💥 爆牌！抽到 {new_card}，当前点数：{dealer_points}"
        elif len(self.session.dealer_cards) == 5 and dealer_points <= 21:
            self.session.dealer_state = PlayerState.FIVE_DRAGON
            message = f"🐉 五小龙！抽到 {new_card}，当前点数：{dealer_points}"
        else:
            message = f"🎴 抽到 {new_card}，当前点数：{dealer_points}"
        
        return {"success": True, "message": message}
    
    async def handle_dealer_stand(self) -> dict:
        """处理庄家停牌"""
        if self.session.dealer_state != PlayerState.PLAYING:
            return {"success": False, "message": "您已完成操作"}
        
        self.session.dealer_state = PlayerState.STAND
        dealer_points = G21Logic.calculate_points(self.session.dealer_cards)
        return {"success": True, "message": f"🛑 停牌成功，当前点数：{dealer_points}"}
    
    async def handle_hit(self, user_id: int) -> dict:
        player = self.session.get_player(user_id)
        if not player: return {"success": False, "message": "您不在游戏中"}
        
        async with player['lock']:
            if player['state'] != PlayerState.PLAYING:
                return {"success": False, "message": "您已完成操作"}
            
            new_card = G21Logic.deal_card(self.session.deck)
            if not new_card: return {"success": False, "message": "牌堆已空"}
            
            player['cards'].append(new_card)
            player['points'] = G21Logic.calculate_points(player['cards'])
            
            if player['points'] > 21:
                player['state'] = PlayerState.BUST
                message = f"💥 爆牌！抽到 {new_card}，当前点数：{player['points']}"
            elif len(player['cards']) == 5 and player['points'] <= 21:
                player['state'] = PlayerState.FIVE_DRAGON
                message = f"🐉 五小龙！抽到 {new_card}，当前点数：{player['points']}"
            else:
                message = f"🎴 抽到 {new_card}，当前点数：{player['points']}"
            
            return {"success": True, "message": message}
    
    async def handle_stand(self, user_id: int) -> dict:
        player = self.session.get_player(user_id)
        if not player: return {"success": False, "message": "您不在游戏中"}
        
        async with player['lock']:
            if player['state'] != PlayerState.PLAYING:
                return {"success": False, "message": "您已完成操作"}
            player['state'] = PlayerState.STAND
            return {"success": True, "message": f"🛑 停牌成功，当前点数：{player['points']}"}
    
    async def create_dealer_scoreboard(self, client: Client, group_id: int) -> int:
        """创建庄家操作阶段的看板"""
        message_text = ScoreboardRenderer.render_dealer_action_scoreboard(
            self.session.dealer_user_id,
            self.session.dealer_name,
            self.session.dealer_cards,
            self.session.players,
            self.session.dealer_remaining
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎴 要牌", callback_data=f"mpg21_dealer_hit_{group_id}"),
             InlineKeyboardButton("🛑 停牌", callback_data=f"mpg21_dealer_stand_{group_id}")]
        ])
        message = await client.send_message(chat_id=group_id, text=message_text, reply_markup=keyboard)
        self.session.scoreboard_message_id = message.id
        return message.id
    
    async def create_player_scoreboard(self, client: Client, group_id: int) -> int:
        """创建玩家操作阶段的看板"""
        message_text = ScoreboardRenderer.render_player_action_scoreboard(
            self.session.dealer_user_id, self.session.dealer_name, self.session.dealer_cards, self.session.players, self.session.action_remaining, hide_dealer_second=True
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎴 要牌", callback_data=f"mpg21_hit_{group_id}"),
             InlineKeyboardButton("🛑 停牌", callback_data=f"mpg21_stand_{group_id}")]
        ])
        message = await client.send_message(chat_id=group_id, text=message_text, reply_markup=keyboard)
        self.session.scoreboard_message_id = message.id
        return message.id
    
    async def update_player_scoreboard(self, client: Client):
        """更新玩家操作阶段的看板"""
        if not self.session.scoreboard_message_id: return
        message_text = ScoreboardRenderer.render_player_action_scoreboard(
            self.session.dealer_user_id, self.session.dealer_name, self.session.dealer_cards, self.session.players, self.session.action_remaining, hide_dealer_second=True
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎴 要牌", callback_data=f"mpg21_hit_{self.session.group_id}"),
             InlineKeyboardButton("🛑 停牌", callback_data=f"mpg21_stand_{self.session.group_id}")]
        ])
        try:
            await client.edit_message_text(
                chat_id=self.session.group_id, message_id=self.session.scoreboard_message_id,
                text=message_text, reply_markup=keyboard
            )
        except MessageNotModified:
            pass 
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception: pass
    
    async def start_batch_update_loop(self, client: Client):
        while self.session.phase == GamePhase.PLAYER_ACTION:
            await asyncio.sleep(4)
            if self.session.phase != GamePhase.PLAYER_ACTION: break
            await self.update_player_scoreboard(client)
    
    def check_all_players_done(self) -> bool:
        for player in self.session.players:
            if player['state'] == PlayerState.PLAYING: return False
        return True


class ResolutionManager:
    def __init__(self, session: G21Session):
        self.session = session
    
    async def settle_single_player(self, player: dict) -> dict:
        player_points = player['points']
        dealer_points = G21Logic.calculate_points(self.session.dealer_cards)
        bet_amount = player['bet_amount']
        user_id = player['user_id']
        
        # 核心胜负判定 (平局算庄家赢)
        if player['state'] == PlayerState.BUST:
            result, payout, win_type = "LOSE", 0, None
        elif player['state'] == PlayerState.BLACKJACK:
            if dealer_points == 21 and len(self.session.dealer_cards) == 2:
                result, payout, win_type = "LOSE", 0, "TIE_LOSS" # 双方BJ，庄赢
            else:
                result, payout, win_type = "WIN", int(bet_amount * 1.5), "BLACKJACK"
        elif player['state'] == PlayerState.FIVE_DRAGON:
            if len(self.session.dealer_cards) == 5 and dealer_points <= 21:
                result, payout, win_type = "LOSE", 0, "TIE_LOSS" # 双方五龙，庄赢
            else:
                result, payout, win_type = "WIN", bet_amount * 2, "FIVE_DRAGON"
        elif dealer_points > 21:
            result, payout, win_type = "WIN", bet_amount, "NORMAL"
        elif player_points > dealer_points:
            result, payout, win_type = "WIN", bet_amount, "NORMAL"
        else:
            result, payout, win_type = "LOSE", 0, "TIE_LOSS" if player_points == dealer_points else None
        
        # 更新玩家余额
        max_retries = 3
        for _ in range(max_retries):
            try:
                user = sql_get_emby(user_id)
                if user:
                    if result == "WIN": 
                        sql_update_emby(Emby.tg == user_id, iv=user.iv + bet_amount + payout)
                    break
            except:
                await asyncio.sleep(1)
        
        if result == "WIN":
            self.session.dealer_net_profit -= payout
        else:
            self.session.dealer_net_profit += bet_amount
        
        return {
            "user_id": user_id, "username": player['username'], "bet_amount": bet_amount,
            "result": result, "win_type": win_type, "payout": payout,
            "player_points": player_points, "dealer_points": dealer_points
        }
    
    async def settle_all_players(self) -> List[dict]:
        results = []
        for player in self.session.players:
            results.append(await self.settle_single_player(player))
        
        # 按赚取金币数量排序（从高到低）
        def get_net_profit(result):
            if result['result'] == "WIN":
                return result['payout']  # 赢家：赚取的金币（正数）
            else:
                return -result['bet_amount']  # 输家：损失的金币（负数）
        
        results.sort(key=get_net_profit, reverse=True)
            
        max_retries = 3
        for _ in range(max_retries):
            try:
                dealer_user = sql_get_emby(self.session.dealer_user_id)
                if dealer_user:
                    new_iv = dealer_user.iv + self.session.dealer_net_profit
                    sql_update_emby(Emby.tg == self.session.dealer_user_id, iv=new_iv)
                    break
            except:
                await asyncio.sleep(1)
                
        return results
    
    async def send_settlement_message(self, client: Client, group_id: int, results: List[dict]):
            message_text = ScoreboardRenderer.render_settlement(
                self.session.dealer_user_id,  # 添加庄家用户ID参数
                self.session.dealer_name, 
                self.session.dealer_net_profit, 
                results, 
                self.session.dealer_cards
            )
            try:
                message = await client.send_message(chat_id=group_id, text=message_text)
                asyncio.create_task(delete_message_after_delay(client, group_id, message.id, 180))
            except: pass


# ==================== 指令与回调处理器 ====================

@bot.on_message(filters.command('startg21', prefixes=prefixes) & filters.group)
async def handle_startg21_command(client: Client, message: Message):
    if not game.g21_open: return
    try: await message.delete()
    except: pass
    
    user_id = message.from_user.id
    username = message.from_user.first_name or f"用户{user_id}"
    group_id = message.chat.id
    
    try:
        user = sql_get_emby(user_id)
        if not user:
            x = await message.reply_text("❌ 您还未在系统中初始化，请先私信我激活")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
            
        if not game.g21_no_emby and not user.embyid:
            x = await message.reply_text("❌ 您还未注册Emby账户")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
            
        if user.iv <= 0:
            x = await message.reply_text("❌ 余额不足，无法坐庄！")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
            
        global _monitor_task_started
        if not _monitor_task_started:
            asyncio.create_task(monitor_session_timeout())
            _monitor_task_started = True

        if group_id in active_g21_games:
            x = await message.reply_text("❌ 当前群组已有进行中的牌局，请先完成！")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
            
        session = G21Session(group_id, user_id, username)
        active_g21_games[group_id] = session
        
        lobby_manager = LobbyManager(session)
        await lobby_manager.create_lobby_panel(client, group_id)
        session.countdown_task = asyncio.create_task(lobby_manager.start_countdown(client, session.lobby_timeout))
        
        try: await client.send_message(user_id, f"✅ 您已成功发起一局21点并担任庄家！")
        except: pass
        
    except Exception as e:
        LOGGER.error(f"处理 /startg21 失败: {e}")


@bot.on_message(filters.command('g21', prefixes=prefixes) & filters.group)
async def handle_g21_command(client: Client, message: Message):
    if not game.g21_open: return
    try: await message.delete()
    except: pass
    
    user_id = message.from_user.id
    username = message.from_user.first_name or f"用户{user_id}"
    group_id = message.chat.id
    command_text = message.text or ""
    
    try:
        if group_id not in active_g21_games:
            x = await message.reply_text("❌ 当前没有筹备中的牌局，请发送 /startg21 发起游戏")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
            
        session = active_g21_games[group_id]
        
        if session.dealer_user_id == user_id:
            x = await message.reply_text("❌ 您是本局庄家，无法作为玩家下注！")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))

        user = sql_get_emby(user_id)
        if not user: return
        
        parse_result = CommandParser.parse_g21_command(command_text, user.iv)
        if not parse_result['success']:
            x = await message.reply_text(f"❌ {parse_result['error_message']}")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
        
        bet_amount = parse_result['bet_amount']
        
        if user.iv < bet_amount:
            x = await message.reply_text(f"❌ 余额不足！当前余额：{user.iv} {sakura_b}")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
        
        try:
            sql_update_emby(Emby.tg == user_id, iv=user.iv - bet_amount)
        except Exception:
            x = await message.reply_text("❌ 系统错误，请稍后再试")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
        
        result = await session.add_player(user_id, username, bet_amount)
        if not result['success']:
            try: sql_update_emby(Emby.tg == user_id, iv=user.iv) 
            except: pass
            x = await message.reply_text(f"❌ {result['message']}")
            return asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
        
        # 如果是追加筹码，发送追加成功消息
        if result.get('is_additional'):
            x = await message.reply_text(
                f"✅ 追加成功！\n"
                f"原下注：{result['old_bet']} {sakura_b}\n"
                f"追加金额：{result['additional_amount']} {sakura_b}\n"
                f"当前总下注：{result['new_total']} {sakura_b}"
            )
            asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
        
        await LobbyManager(session).update_lobby_panel(client)
        
        if len(session.players) >= 20:
            await session.start_dealer_action_phase(client)
        
    except Exception as e:
        LOGGER.error(f"处理 /g21 失败: {e}")


@bot.on_callback_query(filters.regex(r"^mpg21_quit_"))
async def handle_lobby_quit_callback(client: Client, call: CallbackQuery):
    try:
        group_id = int(call.data.split('_')[2])
        user_id = call.from_user.id
        
        if group_id not in active_g21_games:
            return await call.answer("❌ 游戏不存在", show_alert=True)
        session = active_g21_games[group_id]
        
        if session.phase != GamePhase.LOBBY:
            return await call.answer("❌ 游戏已开始，无法退出", show_alert=True)
            
        # 1. 庄家点击解散
        if session.dealer_user_id == user_id:
            penalty = 0
            # 只有在有玩家上车的情况下，解散才会有惩罚
            if len(session.players) > 0:
                penalty = 100
                try:
                    dealer_user = sql_get_emby(user_id)
                    if dealer_user:
                        sql_update_emby(Emby.tg == user_id, iv=dealer_user.iv - penalty)
                except: pass
            
            # 解散房间，所有上车玩家全额退款
            await session.cleanup(client, refund_all=True)
            
            if penalty > 0:
                await call.answer(f"✅ 您已强制解散游戏，扣除违约金 {penalty} {sakura_b}，玩家筹码已退还", show_alert=True)
                x = await client.send_message(group_id, f"🛑 庄家 {session.dealer_name} 强制解散了游戏，已被扣除 {penalty} {sakura_b} 违约金。所有玩家筹码已退回。")
            else:
                await call.answer("✅ 您已取消本局游戏", show_alert=False)
                x = await client.send_message(group_id, f"🛑 庄家 {session.dealer_name} 取消了游戏。")
                
            asyncio.create_task(delete_message_after_delay(client, group_id, x.id, 10))
            return

        # 2. 玩家点击退出
        if not session.is_player_in_game(user_id):
            return await call.answer("❌ 您不在游戏中", show_alert=False)
        
        # 扣除 20% 作为下车惩罚
        result = await session.remove_player(user_id, penalty_rate=0.2)
        if result['success']:
            await call.answer(
                f"✅ 退出成功！扣除违约金 {result['penalty_amount']}，退还 {result['refund_amount']} {sakura_b}", 
                show_alert=True
            )
            await LobbyManager(session).update_lobby_panel(client)
        else:
            await call.answer("❌ 退出失败", show_alert=True)
            
    except: pass


@bot.on_callback_query(filters.regex(r"^mpg21_dealer_hit_"))
async def handle_dealer_hit_callback(client: Client, call: CallbackQuery):
    """处理庄家要牌回调"""
    try:
        group_id = int(call.data.split('_')[3])
        user_id = call.from_user.id
        
        if group_id not in active_g21_games:
            return await call.answer("❌ 游戏不存在", show_alert=True)
        
        session = active_g21_games[group_id]
        
        if session.phase != GamePhase.DEALER_ACTION:
            return await call.answer("❌ 不在庄家操作阶段", show_alert=True)
        
        if session.dealer_user_id != user_id:
            return await call.answer("❌ 只有庄家可以操作", show_alert=True)
        
        action_controller = ActionPhaseController(session)
        result = await action_controller.handle_dealer_hit()
        await call.answer(result['message'], show_alert=False)
        
        # 更新庄家私聊消息
        await action_controller.send_dealer_private_message(client)
        
        # 如果庄家完成操作，进入玩家操作阶段
        if session.dealer_state != PlayerState.PLAYING:
            await session.start_player_action_phase(client)
    except:
        pass


@bot.on_callback_query(filters.regex(r"^mpg21_dealer_stand_"))
async def handle_dealer_stand_callback(client: Client, call: CallbackQuery):
    """处理庄家停牌回调"""
    try:
        group_id = int(call.data.split('_')[3])
        user_id = call.from_user.id
        
        if group_id not in active_g21_games:
            return await call.answer("❌ 游戏不存在", show_alert=True)
        
        session = active_g21_games[group_id]
        
        if session.phase != GamePhase.DEALER_ACTION:
            return await call.answer("❌ 不在庄家操作阶段", show_alert=True)
        
        if session.dealer_user_id != user_id:
            return await call.answer("❌ 只有庄家可以操作", show_alert=True)
        
        action_controller = ActionPhaseController(session)
        result = await action_controller.handle_dealer_stand()
        await call.answer(result['message'], show_alert=False)
        
        # 进入玩家操作阶段
        await session.start_player_action_phase(client)
    except:
        pass


@bot.on_callback_query(filters.regex(r"^mpg21_hit_"))
async def handle_hit_callback(client: Client, call: CallbackQuery):
    try:
        group_id = int(call.data.split('_')[2])
        user_id = call.from_user.id
        
        if group_id not in active_g21_games: return await call.answer("❌ 游戏不存在", show_alert=True)
        session = active_g21_games[group_id]
        
        if session.phase != GamePhase.PLAYER_ACTION: return await call.answer("❌ 不在玩家操作阶段", show_alert=True)
        
        if not session.is_player_in_game(user_id): return await call.answer("❌ 您不在游戏中", show_alert=False)
        
        action_controller = ActionPhaseController(session)
        result = await action_controller.handle_hit(user_id)
        await call.answer(result['message'], show_alert=False)
        
        if result['success'] and action_controller.check_all_players_done():
            await session.start_resolution_phase(client)
    except: pass


@bot.on_callback_query(filters.regex(r"^mpg21_stand_"))
async def handle_stand_callback(client: Client, call: CallbackQuery):
    try:
        group_id = int(call.data.split('_')[2])
        user_id = call.from_user.id
        
        if group_id not in active_g21_games: return await call.answer("❌ 游戏不存在", show_alert=True)
        session = active_g21_games[group_id]
        
        if session.phase != GamePhase.PLAYER_ACTION: return await call.answer("❌ 不在玩家操作阶段", show_alert=True)
        
        if not session.is_player_in_game(user_id): return await call.answer("❌ 您不在游戏中", show_alert=False)
        
        action_controller = ActionPhaseController(session)
        result = await action_controller.handle_stand(user_id)
        await call.answer(result['message'], show_alert=False)
        
        if result['success'] and action_controller.check_all_players_done():
            await session.start_resolution_phase(client)
    except: pass


# ==================== 辅助任务 ====================

async def delete_message_after_delay(client: Client, chat_id: int, message_id: int, delay: int):
    await asyncio.sleep(delay)
    try: await client.delete_messages(chat_id, message_id)
    except: pass


async def monitor_session_timeout():
    """监控会话超时（5分钟强制清理，防卡死）"""
    while True:
        await asyncio.sleep(60)
        current_time = time.time()
        expired_sessions = []
        
        for group_id, session in active_g21_games.items():
            if current_time - session.created_at > 300: 
                expired_sessions.append(group_id)
        
        for group_id in expired_sessions:
            LOGGER.warning(f"清理过期会话 - 群组ID: {group_id}")
            session = active_g21_games[group_id]
            await session.cleanup(bot, refund_all=True)