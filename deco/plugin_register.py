from botoy import GroupMsg, S
from ..cmd_server import plugin_manager


def plugin_register(name: str):
    def deco(func):
        def inner(ctx: GroupMsg):
            ret = None
            h_plugin = plugin_manager(name)
            if h_plugin.bind(ctx):
                ret = func(ctx)

                if ret:
                    h_plugin.app_usage(ctx.FromUserId)
            return ret

        return inner

    return deco
