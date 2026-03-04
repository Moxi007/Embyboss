import asyncio
from pyrogram import filters
from bot import bot, LOGGER
from bot.func_helper.captcha import verify_math_captcha
from bot.func_helper.msg_utils import callAnswer, editMessage

class MockMsg:
    """为了兼容旧的基于msg传参的逻辑伪造一个Message对像"""
    def __init__(self, call):
        self.from_user = call.from_user
        self.chat = call.message.chat
        self.id = call.message.id
        self.delete = call.message.delete
        self.reply = call.message.reply

@bot.on_callback_query(filters.regex(r'^captcha_(\d+)$'))
async def on_captcha(_, call):
    selected_ans = int(call.matches[0].group(1))
    success, req = verify_math_captcha(call.from_user.id, selected_ans)
    
    if not req:
        return await callAnswer(call, "⚠️ 验证码已过期或无效，请重新发起操作。", True)
        
    if not success:
        await editMessage(call, "❌ 答案错误！请求已被拒绝。")
        return await callAnswer(call, "❌ 答案错误！请求已被拒绝。", True)
        
    await callAnswer(call, "✅ 验证通过，处理中...", False)
    
    action = req.get("action")
    payload = req.get("payload", {})
    
    if action == "create":
        from bot.modules.panel.member_panel import create
        # 传递给原有的创建账户接口，继续往下走
        await create(_, call, passed_captcha=True)

    elif action == "rgs_code":
        from bot.modules.commands.exchange import rgs_code
        mock_msg = MockMsg(call)
        await call.message.delete()
        await rgs_code(_, mock_msg, register_code=payload.get("code"), passed_captcha=True)
