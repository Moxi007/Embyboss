import sys
try:
    from bot import bot
    from bot.modules.panel import *
    from bot.modules.commands import *
    from bot.modules.extra import *
    from bot.modules.callback import *
    from bot.web import *
    print("All imports successful")
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
