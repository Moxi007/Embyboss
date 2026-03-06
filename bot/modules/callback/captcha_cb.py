import asyncio
from pyrogram import filters
from bot import bot, LOGGER
from bot.func_helper.captcha import verify_math_captcha, generate_math_captcha
from bot.func_helper.msg_utils import callAnswer, editMessage

class MockMsg:
    """为了兼容旧的基于msg传参的逻辑伪造一个Message对像"""
    def __init__(self, call):
        self.from_user = call.from_user
        self.chat = call.message.chat
        self.id = call.message.id
        self.delete = call.message.delete
        self.reply = call.message.reply
        self.text = ""

@bot.on_callback_query(filters.regex(r'^captcha_(\d+)$'))
async def on_captcha(_, call):
    selected_ans = int(call.matches[0].group(1))
    success, can_continue, left_tries, req = verify_math_captcha(call.from_user.id, selected_ans)
    
    if not can_continue and not req:
        return await callAnswer(call, "⚠️ 验证码已过期或无效，请重新发起操作。", True)
        
    if not can_continue and req:
        await editMessage(call, "❌ 错误次数过多！请求已被拒绝。")
        return await callAnswer(call, "❌ 错误次数过多或无效！请求已被拒绝。", True)
        
    if not success and can_continue:
        # 答错了但是还有机会，重新发一份验证码覆盖
        action = req.get("action")
        payload = req.get("payload", {})
        
        # 为了保留已有的重试次数，我们需要先取出来再放回去（generate_math_captcha内部默认归0）
        # 对此，我们可以直接在这进行原题重载。但为了防止被暴力利用，我们可以让其重新生题。
        # 更好的做法是在这里直接让题目重出。
        question, keyboard = generate_math_captcha(call.from_user.id, action, payload)
        # 修复刚重新生成的缓存覆盖问题，把错误次数再回写。
        from bot.func_helper.captcha import captcha_cache
        new_req = captcha_cache.get(f"captcha_req_{call.from_user.id}")
        if new_req:
            new_req["tries"] = 3 - left_tries
            captcha_cache.set(f"captcha_req_{call.from_user.id}", new_req)
            
        await editMessage(call, f"❌ 答案错误！您还有 {left_tries} 次机会。\n\n🤖 **防机器人验证**\n重新计算以下算式：\n\n**{question}**", buttons=keyboard)
        return await callAnswer(call, f"❌ 答案错误！您还有 {left_tries} 次机会。", True)
        
    await callAnswer(call, "✅ 验证通过，处理中...", False)
    
    action = req.get("action")
    payload = req.get("payload", {})
    
    if action == "rgs_code":
        from bot.modules.commands.exchange import rgs_code
        # 发出的验证码由于改在了私聊发出，所以其回答后的载体变成了私密聊天
        mock_msg = MockMsg(call)
        await call.message.delete()
        await rgs_code(_, mock_msg, register_code=payload.get("code"), passed_captcha=True)
    else:
        # 未知 action，清理验证码消息
        try:
            await call.message.delete()
        except Exception:
            pass
