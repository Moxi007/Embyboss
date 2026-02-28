# 重启
from bot import LOGGER, bot, config, save_config
from pyrogram.errors import BadRequest


# 定义一个检查函数
async def check_restart():
    if config.schedall.restart_chat_id != 0:
        chat_id, msg_id = config.schedall.restart_chat_id, config.schedall.restart_msg_id
        up_description = config.auto_update.up_description if config.auto_update.up_description else ""
        text = 'Restarted Successfully!\n\n' + up_description
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=text)
        except BadRequest:
            await bot.send_message(chat_id=chat_id, text=text)
        LOGGER.info(f"目标：{chat_id} 消息id：{msg_id} 已提示重启成功")
        config.schedall.restart_chat_id = 0
        config.schedall.restart_msg_id = 0
        config.auto_update.up_description = None
        save_config()

    else:
        LOGGER.info("未检索到有重启指令，直接启动")
