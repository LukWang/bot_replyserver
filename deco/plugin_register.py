from botoy import GroupMsg, S
from ..cmd_server import plugin_manager
import re


def plugin_register(name: str, help_content=""):
    def deco(func):
        def inner(ctx: GroupMsg):
            ret = None
            h_plugin = plugin_manager(name)
            if h_plugin.bind(ctx):
                if re.match(f"^帮助\s*{name}$", ctx.Content):
                    sender = S.bind(ctx)
                    if len(help_content):
                        sender.text(help_content)
                    else:
                        sender.text("没有找到帮助说明\u1F97A")
                else:
                    ret = func(ctx)

                if ret:
                    h_plugin.app_usage(ctx.FromUserId)
            return ret

        return inner

    return deco
