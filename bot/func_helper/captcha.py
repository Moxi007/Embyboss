import random
from cacheout import Cache
from pyromod.helpers import array_chunk, ikb

# 验证码全局缓存，存活期120秒，最多处理2000个并发验证验证请求。
captcha_cache = Cache(maxsize=2000, ttl=120)

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
    captcha_cache.set(f"captcha_req_{user_id}", {"ans": ans, "action": action, "payload": payload or {}})
    return question, keyboard

def verify_math_captcha(user_id: int, selected_ans: int):
    """
    验证数学验证码，验证成功后返回 true 及 payload，验证失败返回 false 及 payload。
    """
    req = captcha_cache.get(f"captcha_req_{user_id}")
    if not req:
        return False, None
    if req["ans"] == selected_ans:
        captcha_cache.delete(f"captcha_req_{user_id}")
        return True, req
    return False, req
