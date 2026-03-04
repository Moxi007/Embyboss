import asyncio
from pyrogram import filters
from bot import bot, LOGGER
from bot.func_helper.captcha import verify_math_captcha
from bot.func_helper.msg_utils import callAnswer, editMessage

class MockChat:
    def __init__(self, chat_id):
        self.id = chat_id
        self.type = "private"

class MockMsg:
    """为了兼容旧的基于msg传参的逻辑伪造一个Message对像"""
    def __init__(self, call):
        self.from_user = call.from_user
        self.chat = MockChat(call.from_user.id)
        self.id = call.message.id
        self.delete = call.message.delete
        self.reply = call.message.reply
        self.text = ""

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
        # 如果是在私聊答题的，我们没有了原先面板那里的界面用于 editMessage，因此提供一个新的MockMsg模拟私有对话的Call环境
        class MockCall:
            def __init__(self, original_call):
                self.from_user = original_call.from_user
                self.message = original_call.message
                self.data = 'create'
            
            async def answer(self, text="", show_alert=False, url="", cache_time=0):
                return True
                
        mock_call = MockCall(call)
        await call.message.delete()
        await create(_, mock_call, passed_captcha=True)

    elif action == "rgs_code":
        from bot.modules.commands.exchange import rgs_code
        # 发出的验证码由于改在了私聊发出，所以其回答后的载体变成了私密聊天
        mock_msg = MockMsg(call)
        await call.message.delete()
        await rgs_code(_, mock_msg, register_code=payload.get("code"), passed_captcha=True)
