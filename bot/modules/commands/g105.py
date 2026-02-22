"""
十点半扑克游戏模块

这是一个基于 Telegram Bot 的扑克牌游戏，玩家通过命令发起游戏并下注，
目标是让手牌点数尽可能接近 10.5 但不超过。
"""

import asyncio
import random
from datetime import datetime
from typing import Dict, List
from pyrogram import filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from bot import bot, prefixes, sakura_b, game, LOGGER
from bot.func_helper.msg_utils import deleteMessage
from bot.sql_helper.sql_emby import sql_get_emby, sql_update_emby, Emby

# 存储活跃游戏的字典 (user_id -> game_state)
active_g105_games: Dict[int, Dict] = {}


class G105Logic:
    """十点半游戏核心逻辑类"""
    
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
        deck = [f"{suit}{rank}" for suit in G105Logic.SUITS for rank in G105Logic.RANKS]
        
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
    def calculate_points(cards: List[str]) -> float:
        """
        计算手牌总点数
        
        规则:
            - A: 1点
            - 2-9: 牌面点数
            - 10/J/Q/K: 0.5点
        
        参数:
            cards: 手牌列表
        
        返回:
            总点数（支持小数）
        """
        total = 0.0
        for card in cards:
            # 去掉花色符号，获取点数
            rank = card[1:]
            if rank == 'A':
                total += 1.0
            elif rank in ['10', 'J', 'Q', 'K']:
                total += 0.5
            else:
                total += float(rank)
        return total

    
    @staticmethod
    def dealer_auto_draw(dealer_cards: List[str], deck: List[str]) -> List[str]:
        """
        庄家自动抽牌逻辑
        
        规则: 点数 < 7 时继续抽牌
        
        参数:
            dealer_cards: 庄家当前手牌
            deck: 剩余牌堆
        
        返回:
            更新后的庄家手牌
        """
        while True:
            points = G105Logic.calculate_points(dealer_cards)
            
            # 停止条件：点数达到7或以上、爆牌、或达到5张牌
            if points >= 7 or points > 10.5 or len(dealer_cards) >= 5:
                break
            
            # 抽牌
            if deck:
                card = G105Logic.deal_card(deck)
                if card:
                    dealer_cards.append(card)
                else:
                    break
            else:
                break  # 牌堆空了
        
        return dealer_cards

    
    @staticmethod
    def judge_winner(player_points: float, dealer_points: float,
                     player_cards: List[str], dealer_cards: List[str]) -> dict:
        """
        判定胜负
        
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
                'player_points': float,
                'dealer_points': float,
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
        if player_points > 10.5:
            result['winner'] = 'dealer'
            result['reason'] = '玩家爆牌'
            return result
        
        # 2. 玩家五小龙
        if len(player_cards) == 5 and player_points <= 10.5:
            result['is_five_dragon'] = True
            if len(dealer_cards) != 5 or dealer_points > 10.5:
                result['winner'] = 'player'
                result['reason'] = '玩家五小龙'
                result['multiplier'] = 2.0
                return result
        
        # 3. 庄家爆牌
        if dealer_points > 10.5:
            result['winner'] = 'player'
            result['reason'] = '庄家爆牌'
            result['multiplier'] = 1.0
            return result
        
        # 4. 庄家五小龙
        if len(dealer_cards) == 5 and dealer_points <= 10.5:
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



def generate_game_message(game: dict, show_dealer_cards: bool = False) -> str:
    """
    生成游戏界面消息
    
    参数:
        game: 游戏状态
        show_dealer_cards: 是否显示庄家所有牌
    
    返回:
        消息文本
    """
    player_cards = game['player_cards']
    dealer_cards = game['dealer_cards']
    
    player_points = G105Logic.calculate_points(player_cards)
    dealer_points = G105Logic.calculate_points(dealer_cards)
    
    # 玩家手牌
    player_hand_str = format_hand(player_cards)
    
    # 庄家手牌（可能隐藏第二张）
    dealer_hand_str = format_hand(dealer_cards, hide_second=not show_dealer_cards)
    
    message = f"""🎴 十点半游戏

👤 玩家手牌：{player_hand_str}
📊 玩家点数：{player_points}

🎩 庄家手牌：{dealer_hand_str}
"""
    
    if show_dealer_cards:
        message += f"📊 庄家点数：{dealer_points}\n"
    
    message += f"\n💰 下注金额：{game_state['bet_amount']} {sakura_b}"
    
    return message


def create_game_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """
    创建游戏操作按钮
    
    参数:
        user_id: 用户ID，用于回调数据验证
    
    返回:
        InlineKeyboardMarkup
    """
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎴 要牌", callback_data=f"g105_hit_{user_id}"),
            InlineKeyboardButton("🛑 停牌", callback_data=f"g105_stand_{user_id}")
        ]
    ])



def generate_result_message(game: dict, result: dict, user_balance: int) -> str:
    """
    生成游戏结果消息
    
    参数:
        game: 游戏状态
        result: 胜负判定结果
        user_balance: 用户当前余额
    
    返回:
        消息文本
    """
    player_hand_str = format_hand(game['player_cards'])
    dealer_hand_str = format_hand(game['dealer_cards'])
    
    message = f"""🎴 十点半游戏 - 结果

👤 玩家手牌：{player_hand_str}
📊 玩家点数：{result['player_points']}

🎩 庄家手牌：{dealer_hand_str}
📊 庄家点数：{result['dealer_points']}

"""
    
    # 胜负结果
    if result['winner'] == 'player':
        reward = int(game_state['bet_amount'] * result['multiplier'])
        message += f"🎉 恭喜获胜！\n"
        message += f"📝 原因：{result['reason']}\n"
        message += f"💰 获得：{reward} {sakura_b}\n"
        message += f"💳 当前余额：{user_balance} {sakura_b}\n"
    elif result['winner'] == 'tie':
        message += f"🤝 平局\n"
        message += f"💰 退还：{game['bet_amount']} {sakura_b}\n"
        message += f"💳 当前余额：{user_balance} {sakura_b}\n"
    else:
        message += f"😔 很遗憾，您输了\n"
        message += f"📝 原因：{result['reason']}\n"
        message += f"💸 损失：{game['bet_amount']} {sakura_b}\n"
        message += f"💳 当前余额：{user_balance} {sakura_b}\n"
    
    return message



def parse_g105_command(command_text: str) -> dict:
    """
    解析 /g105 命令
    
    参数:
        command_text: 命令文本
    
    返回:
        {'success': bool, 'amount': int, 'error': str}
    """
    try:
        parts = command_text.split()
        if len(parts) < 2:
            return {
                'success': False,
                'error': '❌ 格式错误！请使用：/g105 [金额]\n例如：/g105 100'
            }
        
        amount_str = parts[1]
        amount = int(amount_str)
        
        if amount < 1:
            return {
                'success': False,
                'error': '❌ 下注金额不能小于 1 金币'
            }
        
        return {
            'success': True,
            'amount': amount
        }
    except ValueError:
        return {
            'success': False,
            'error': '❌ 请输入有效的整数金额'
        }



async def cleanup_g105_game_state(user_id: int, refund: bool = False):
    """
    清理游戏状态，可选退款
    
    参数:
        user_id: 用户ID
        refund: 是否退还下注金额
    """
    try:
        if user_id in active_g105_games:
            game_state = active_g105_games[user_id]
            
            # 取消超时计时器
            if 'timeout_task' in game_state and game_state['timeout_task']:
                try:
                    game_state['timeout_task'].cancel()
                except:
                    pass
            
            # 退款处理
            if refund:
                user = sql_get_emby(user_id)
                if user:
                    new_balance = user.iv + game_state['bet_amount']
                    sql_update_emby(Emby.tg == user_id, iv=new_balance)
            
            # 删除状态
            del active_g105_games[user_id]
            
            LOGGER.info(f"清理游戏状态: user_id={user_id}, refund={refund}")
    except Exception as e:
        LOGGER.error(f"清理游戏状态失败: {e}")


def cancel_g105_timeout_timer(user_id: int):
    """
    取消超时计时器
    
    参数:
        user_id: 用户ID
    """
    try:
        if user_id in active_g105_games:
            game_state = active_g105_games[user_id]
            if 'timeout_task' in game_state and game_state['timeout_task']:
                game_state['timeout_task'].cancel()
                LOGGER.debug(f"取消超时计时器: user_id={user_id}")
    except Exception as e:
        LOGGER.error(f"取消超时计时器失败: {e}")


def reset_g105_timeout_timer(user_id: int, timeout_seconds: int = 60):
    """
    重置超时计时器（取消旧的并启动新的）
    
    每次玩家操作后调用此函数，重新计时 60 秒
    
    参数:
        user_id: 用户ID
        timeout_seconds: 超时秒数（默认60秒）
    """
    try:
        if user_id in active_g105_games:
            # 取消旧的计时器
            cancel_g105_timeout_timer(user_id)
            
            # 启动新的计时器并保存任务引用
            task = asyncio.create_task(start_g105_timeout_timer(user_id, timeout_seconds))
            active_g105_games[user_id]['timeout_task'] = task
            
            LOGGER.debug(f"重置超时计时器: user_id={user_id}")
    except Exception as e:
        LOGGER.error(f"重置超时计时器失败: {e}")


async def handle_g105_timeout(user_id: int, game: dict):
    """
    处理超时
    
    参数:
        user_id: 用户ID
        game: 游戏状态
    """
    try:
        # 记录日志
        LOGGER.warning(f"游戏超时: user_id={user_id}, bet={game['bet_amount']}")
        
        # 发送超时消息
        timeout_msg = (
            f"⏰ 游戏超时\n\n"
            f"您在 60 秒内未完成操作\n"
            f"下注金额不予退还\n"
            f"💸 损失：{game['bet_amount']} {sakura_b}"
        )
        
        try:
            await bot.send_message(user_id, timeout_msg)
        except:
            pass
        
        # 更新游戏消息
        try:
            await bot.edit_message_text(
                chat_id=game['chat_id'],
                message_id=game['message_id'],
                text=f"{generate_game_message(game, show_dealer_cards=True)}\n\n⏰ 游戏已超时"
            )
        except:
            pass
        
        # 清理游戏状态（不退款）
        await cleanup_g105_game_state(user_id, refund=False)
        
    except Exception as e:
        LOGGER.error(f"处理超时失败: {e}")


async def start_g105_timeout_timer(user_id: int, timeout_seconds: int = 60):
    """
    启动超时计时器
    
    参数:
        user_id: 用户ID
        timeout_seconds: 超时秒数（默认60秒）
    """
    await asyncio.sleep(timeout_seconds)
    
    # 检查游戏是否还在进行
    if user_id in active_g105_games:
        game = active_g105_games[user_id]
        await handle_g105_timeout(user_id, game)


async def settle_g105_game(user_id: int, game: dict, result: dict):
    """
    结算游戏
    
    参数:
        user_id: 用户ID
        game: 游戏状态
        result: 胜负判定结果
    """
    try:
        user = sql_get_emby(user_id)
        if not user:
            LOGGER.error(f"结算失败：用户不存在 user_id={user_id}")
            return
        
        # 计算金币变化
        coin_change = 0
        if result['winner'] == 'player':
            coin_change = int(game['bet_amount'] * result['multiplier'])
        elif result['winner'] == 'tie':
            coin_change = game['bet_amount']
        # dealer wins: coin_change = 0 (已扣除)
        
        # 更新余额
        if coin_change > 0:
            new_balance = user.iv + coin_change
            sql_update_emby(Emby.tg == user_id, iv=new_balance)
        else:
            new_balance = user.iv
        
        # 记录日志
        LOGGER.info(
            f"游戏结束: user_id={user_id}, winner={result['winner']}, "
            f"reason={result['reason']}, coin_change={coin_change}, "
            f"balance={new_balance}"
        )
        
        # 生成结果消息
        result_text = generate_result_message(game, result, new_balance)
        
        # 更新游戏消息
        try:
            result_msg = await bot.edit_message_text(
                chat_id=game['chat_id'],
                message_id=game['message_id'],
                text=result_text
            )
            # 180秒后自动删除
            asyncio.create_task(deleteMessage(result_msg, 180))
        except Exception as e:
            LOGGER.error(f"更新游戏消息失败: {e}")
        
        # 发送私信通知
        try:
            await bot.send_message(user_id, result_text)
        except:
            pass
        
        # 清理游戏状态
        await cleanup_g105_game_state(user_id, refund=False)
        
    except Exception as e:
        LOGGER.error(f"结算游戏失败: {e}")
        # 发生错误时尝试退款
        await cleanup_g105_game_state(user_id, refund=True)



@bot.on_message(filters.command('g105', prefixes=prefixes) & filters.group)
async def handle_g105_command(client, message):
    """处理 /g105 命令"""
    # 检查游戏开关
    if not game.g105_open:
        try:
            await message.delete()
        except:
            pass
        return
    
    # 立即删除命令消息
    asyncio.create_task(deleteMessage(message, 0))
    
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_text = message.text or ""
    
    try:
        # 1. 解析命令
        parse_result = parse_g105_command(message_text)
        if not parse_result['success']:
            error_msg = await message.reply_text(parse_result['error'])
            asyncio.create_task(deleteMessage(error_msg, 60))
            return
        
        bet_amount = parse_result['amount']
        
        # 2. 查询用户信息
        user = sql_get_emby(user_id)
        if not user:
            error_msg = await message.reply_text("❌ 您还未在系统中初始化，请先私信我激活")
            asyncio.create_task(deleteMessage(error_msg, 60))
            return
        
        # 3. 检查 embyid 要求
        if not game.g105_no_emby:
            if not user.embyid:
                error_msg = await message.reply_text("❌ 您还未注册Emby账户")
                asyncio.create_task(deleteMessage(error_msg, 60))
                return
        
        # 4. 检查是否已有进行中的游戏
        if user_id in active_g105_games:
            error_msg = await message.reply_text("❌ 您已有进行中的游戏，请先完成当前游戏")
            asyncio.create_task(deleteMessage(error_msg, 60))
            return
        
        # 5. 检查余额
        if user.iv < bet_amount:
            error_msg = await message.reply_text(f"❌ 余额不足！当前余额：{user.iv} {sakura_b}")
            asyncio.create_task(deleteMessage(error_msg, 60))
            return
        
        # 6. 扣除下注金额
        new_balance = user.iv - bet_amount
        sql_update_emby(Emby.tg == user_id, iv=new_balance)
        
        # 发送私信通知
        try:
            await bot.send_message(
                user_id,
                f"✅ 您已成功发起游戏\n💰 下注金额：{bet_amount} {sakura_b}\n💳 当前余额：{new_balance} {sakura_b}"
            )
        except:
            pass
        
        # 7. 创建牌堆并发牌
        deck = G105Logic.create_deck()
        player_cards = [G105Logic.deal_card(deck), G105Logic.deal_card(deck)]
        dealer_cards = [G105Logic.deal_card(deck), G105Logic.deal_card(deck)]
        
        # 8. 创建游戏状态
        game_state = {
            'user_id': user_id,
            'bet_amount': bet_amount,
            'player_cards': player_cards,
            'dealer_cards': dealer_cards,
            'deck': deck,
            'status': 'playing',
            'start_time': datetime.now(),
            'chat_id': chat_id
        }
        
        # 9. 发送游戏界面
        game_text = generate_game_message(game_state, show_dealer_cards=False)
        keyboard = create_game_keyboard(user_id)
        game_msg = await message.reply_text(game_text, reply_markup=keyboard)
        
        # 保存消息ID
        game_state['message_id'] = game_msg.id
        
        # 存储游戏状态
        active_g105_games[user_id] = game_state
        
        # 10. 启动超时计时器并保存任务引用
        timeout_task = asyncio.create_task(start_g105_timeout_timer(user_id, 60))
        game_state['timeout_task'] = timeout_task
        
        # 记录日志
        LOGGER.info(
            f"游戏开始: user_id={user_id}, bet={bet_amount}, "
            f"time={datetime.now().isoformat()}"
        )
        
    except Exception as e:
        LOGGER.error(f"处理 /g105 命令失败: {e}")
        try:
            error_msg = await message.reply_text("❌ 系统错误，请稍后重试")
            asyncio.create_task(deleteMessage(error_msg, 60))
        except:
            pass


@bot.on_callback_query(filters.regex(r"^g105_(hit|stand)_"))
async def handle_g105_callback(client, call):
    """处理游戏按钮回调"""
    try:
        # 解析回调数据
        parts = call.data.split('_')
        if len(parts) < 3:
            await call.answer("❌ 无效的回调数据", show_alert=True)
            return
        
        action = parts[1]  # hit 或 stand
        target_user_id = int(parts[2])
        caller_user_id = call.from_user.id
        
        # 验证操作者
        if caller_user_id != target_user_id:
            await call.answer("❌ 这不是您的游戏", show_alert=False)
            return
        
        # 检查游戏是否存在
        if target_user_id not in active_g105_games:
            await call.answer("❌ 游戏已结束", show_alert=True)
            return
        
        game_state = active_g105_games[target_user_id]
        
        # 检查用户权限
        user = sql_get_emby(caller_user_id)
        if not user:
            await call.answer("❌ 您还未在系统中初始化", show_alert=True)
            return
        
        if not game.g105_no_emby:
            if not user.embyid:
                await call.answer("❌ 您还未注册Emby账户", show_alert=True)
                return
        
        # 处理操作
        if action == 'hit':
            # 要牌
            card = G105Logic.deal_card(game_state['deck'])
            if card:
                game_state['player_cards'].append(card)
            
            player_points = G105Logic.calculate_points(game_state['player_cards'])
            
            # 记录日志
            LOGGER.info(
                f"玩家操作: user_id={target_user_id}, action=hit, "
                f"cards={len(game_state['player_cards'])}, points={player_points}"
            )
            
            # 检查爆牌
            if player_points > 10.5:
                # 爆牌，游戏结束
                result = G105Logic.judge_winner(
                    player_points,
                    G105Logic.calculate_points(game_state['dealer_cards']),
                    game_state['player_cards'],
                    game_state['dealer_cards']
                )
                await settle_g105_game(target_user_id, game_state, result)
                await call.answer("💥 爆牌了！", show_alert=False)
                return
            
            # 检查五小龙
            if len(game_state['player_cards']) == 5 and player_points <= 10.5:
                # 五小龙，触发庄家抽牌
                game_state['dealer_cards'] = G105Logic.dealer_auto_draw(
                    game_state['dealer_cards'],
                    game_state['deck']
                )
                dealer_points = G105Logic.calculate_points(game_state['dealer_cards'])
                
                result = G105Logic.judge_winner(
                    player_points,
                    dealer_points,
                    game_state['player_cards'],
                    game_state['dealer_cards']
                )
                await settle_g105_game(target_user_id, game_state, result)
                await call.answer("🐉 五小龙！", show_alert=False)
                return
            
            reset_g105_timeout_timer(target_user_id, 60)
            
            # 更新游戏界面
            game_text = generate_game_message(game_state, show_dealer_cards=False)
            keyboard = create_game_keyboard(target_user_id)
            try:
                await call.edit_message_text(game_text, reply_markup=keyboard)
            except:
                pass
            
            await call.answer("🎴 已要牌", show_alert=False)
            
        elif action == 'stand':
            # 停牌
            LOGGER.info(f"玩家操作: user_id={target_user_id}, action=stand")
            
            # 庄家自动抽牌
            game_state['dealer_cards'] = G105Logic.dealer_auto_draw(
                game_state['dealer_cards'],
                game_state['deck']
            )
            
            # 判定胜负
            player_points = G105Logic.calculate_points(game_state['player_cards'])
            dealer_points = G105Logic.calculate_points(game_state['dealer_cards'])
            
            result = G105Logic.judge_winner(
                player_points,
                dealer_points,
                game_state['player_cards'],
                game_state['dealer_cards']
            )
            
            # 结算
            await settle_g105_game(target_user_id, game_state, result)
            await call.answer("🛑 已停牌", show_alert=False)
        
    except Exception as e:
        LOGGER.error(f"处理回调失败: {e}")
        try:
            await call.answer("❌ 处理请求时出错", show_alert=True)
        except:
            pass
