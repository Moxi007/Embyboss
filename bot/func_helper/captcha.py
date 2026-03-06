import random
import time
from cacheout import Cache
from pyromod.helpers import array_chunk, ikb

# 验证码全局缓存，存活期120秒，最多处理2000个并发验证验证请求。
captcha_cache = Cache(maxsize=20000, ttl=300)

def generate_math_captcha(user_id: int, action: str, payload: dict = None):
    """
    生成一个数学验证码（内联键盘）和缓存请求。
    """
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    op = random.choice(['+', '-', '*'])
    if op == '+':
        ans = a + b
    elif op == '-':
        if a < b:
            a, b = b, a
        ans = a - b
    else:
        a = random.randint(1, 9)
        b = random.randint(1, 9)
        ans = a * b
        
    question = f"{a} {op} {b} = ?"
    
    options = [ans]
    while len(options) < 6:
        wrong_ans = ans + random.randint(-15, 15)
        if wrong_ans != ans and wrong_ans >= 0 and wrong_ans not in options:
            options.append(wrong_ans)
    
    random.shuffle(options)
    
    buttons = []
    for opt in options:
        buttons.append((str(opt), f"captcha_{opt}"))
    
    # 3个一行
    lines = array_chunk(buttons, 3)
    # 底部取消
    lines.append([("❌ 取消操作", "closeit")])
    keyboard = ikb(lines)
    
    # 存入缓存
    captcha_cache.set(f"captcha_req_{user_id}", {"ans": ans, "action": action, "payload": payload or {}, "tries": 0, "time": time.time()})
    return question, keyboard

def check_active_captcha(user_id: int):
    """
    检查是否有活跃的验证码且未过期（60秒内阻止重发）
    """
    req = captcha_cache.get(f"captcha_req_{user_id}")
    if req and time.time() - req.get("time", 0) < 60:
        return True
    return False

import asyncio
from bot import bot

async def clear_captcha_later(user_id: int, msg_obj=None):
    """
    60秒后自动清理验证码锁，如果传了msg_obj还会尝试删掉验证码消息
    """
    await asyncio.sleep(60)
    # 不管用户点没点，60秒锁定期一过，强制清理掉锁，防止卡死
    req = captcha_cache.get(f"captcha_req_{user_id}")
    if req:
        # 如果还在缓存里说明没被验证通过删除
        captcha_cache.delete(f"captcha_req_{user_id}")
        if msg_obj:
            try:
                await msg_obj.delete()
            except Exception:
                pass

def verify_math_captcha(user_id: int, selected_ans: int):
    """
    验证数学验证码。
    返回: (成功标识, 是否继续许可, 遗留尝试次数, 请求体Payload)
    """
    req = captcha_cache.get(f"captcha_req_{user_id}")
    if not req:
        return False, False, 0, None
        
    if req["ans"] == selected_ans:
        captcha_cache.delete(f"captcha_req_{user_id}")
        return True, True, 0, req
        
    req["tries"] += 1
    left_tries = 3 - req["tries"]
    if left_tries <= 0:
        # 次数耗尽
        captcha_cache.delete(f"captcha_req_{user_id}")
        return False, False, 0, req
    else:
        captcha_cache.set(f"captcha_req_{user_id}", req)
        return False, True, left_tries, req
