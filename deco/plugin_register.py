from botoy import GroupMsg, S
from ..cmd_server import plugin_manager
import re


def plugin_register(name: str, help=""):
    def deco(func):
        def inner(ctx: GroupMsg):
            ret = None
            h_plugin = plugin_manager(name)
            if h_plugin.bind(ctx):
                if re.match(f"^帮助\s*{name}$", ctx.Content):
                    sender = S.bind(ctx)
                    sender.text(help)
                else:
                    ret = func(ctx)

                if ret:
                    h_plugin.app_usage(ctx.FromUserId)
            return ret

        return inner

    return deco
