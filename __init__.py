from botoy import MsgTypes, S, GroupMsg, FriendMsg
from botoy.sugar import Picture, Text
from botoy.parser import friend, group
from botoy.decorators import ignore_botself
from botoy.session import SessionHandler, session, FILTER_SUCCESS, ctx
import re
from .cmd_server import reply_server, PicObj, REPLY_TYPE
from .cmd_dbi import CMD_TYPE
import time

__doc__ = """图片存储助手"""


def session_filter(ctx):
    if re.match('^_savepic.{1,}',ctx.Content):
        return FILTER_SUCCESS


l_session = SessionHandler(ignore_botself, session_filter, single_user=True, expiration = 30)
l_reply_server = reply_server()


@l_session.parse
def _par(ctx):
    if ctx.MsgType != MsgTypes.PicMsg:
        return ctx.Content

    pic_obj = PicObj()
    if isinstance(ctx, FriendMsg):
        pics = friend.pic(ctx)
        pic_obj.user = ctx.FromUin
        pic_obj.Url = pics.FriendPic[0].Url
        pic_obj.Md5 = pics.FriendPic[0].FileMd5
    elif isinstance(ctx, GroupMsg):
        pics = group.pic(ctx)
        pic_obj.user = ctx.FromUserId
        pic_obj.Url = pics.GroupPic[0].Url
        pic_obj.Md5 = pics.GroupPic[0].FileMd5

    return pic_obj
        

@l_session.handle
def _h():
    prefix = '_savepic'
    cmd = ctx.Content[len(prefix):]
    if l_reply_server.checkout(cmd, cmd_type=CMD_TYPE.PIC, create = True):
        session.send_text('开启{}存储模式，请发送图片'.format(cmd))
    else:
        session.send_text('访问{}图片仓库失败'.format(cmd))
        l_session.finish()
        return
   
    timeout = session._expiration
    last = time.monotonic()
    while True:
        if time.monotonic() - last > timeout:
            session.send_text('因对方无响应，存储模式关闭')
            l_session.finish()
            break
        item = session.pop('pic', wait = True, timeout=1)
        if not item:
            continue
        
        last = time.monotonic()
        if isinstance(item, PicObj):
            ret = l_reply_server.save_pic(item)
            if not ret:
                session.send_text('保存图片失败')
            else:
                session.send_text('保存图片成功')
        elif item == 'end':
            session.send_text('存储模式已关闭')
            l_session.finish()
            break
        else:
            session.send_text('无效参数')


@ignore_botself
def main(ctx):
    l_session.message_receiver(ctx)
    if not l_session.sc.session_existed(ctx, True):
        l_reply_server.handle_cmd(ctx)
        reply_type = l_reply_server.reply_type
        if reply_type == REPLY_TYPE.PIC_MD5:
            Picture(pic_md5=l_reply_server.reply)
        elif reply_type == REPLY_TYPE.PIC_PATH:
            Picture(pic_path=l_reply_server.reply)
        elif reply_type == REPLY_TYPE.TEXT:
            Text(l_reply_server.reply)


receive_group_msg=receive_friend_msg=main
