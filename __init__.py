from botoy import MsgTypes, S, GroupMsg, FriendMsg
from botoy.sugar import Picture
from botoy.parser import friend, group
from botoy.decorators import  ignore_botself
from botoy.session import SessionHandler, session, FILTER_SUCCESS, ctx
import re
from .pic_server import pic_server, PicObj
import time

__doc__ = """图片存储助手"""

def session_filter(ctx):
    if re.match('^save_.{1,}',ctx.Content):
        return FILTER_SUCCESS

l_session = SessionHandler(ignore_botself, session_filter, single_user=True, expiration = 30)
l_pic_server = pic_server()

@l_session.parse
def _par(ctx):
    if ctx.MsgType != MsgTypes.PicMsg:
        return ctx.Content

    pic_obj = PicObj()
    if isinstance(ctx, FriendMsg):
        pics = friend.pic(ctx)
        pic_obj.Url = pics.FriendPic[0].Url
        pic_obj.Md5 = pics.FriendPic[0].FileMd5
    elif isinstance(ctx, GroupMsg):
        pics = group.pic(ctx)
        pic_obj.Url = pics.GroupPic[0].Url
        pic_obj.Md5 = pics.GroupPic[0].FileMd5

    return pic_obj
        
     

@l_session.handle
def _h():
    prefix = 'save_'
    cate = ctx.Content[len(prefix):]
    if l_pic_server.checkout(cate, create = True):
        session.send_text('开启{}存储模式，请发送图片'.format(cate))
    else:
        session.send_text('访问{}图片仓库失败'.format(cate))
        l_session.finish()
        return
   
    timeout = session._expiration
    last = time.monotonic()
    while True:
        if time.monotonic() - last > timeout:
            session.send_text('因对方无响应，存储模式关闭')
            l_session.finish()
            break
        item = session.pop('pic', wait = True, timeout = 1.0)
        if not item:
            continue
        
        last = time.monotonic()
        if isinstance(item, PicObj):
            ret = l_pic_server.save_pic(item)
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
        try_send_pic(ctx)

def try_send_pic(ctx):
    if l_pic_server.checkout(ctx.Content):
        #file_name = l_pic_server.random_pic_path()
        file_name = l_pic_server.random_pic_md5()
        file_name = file_name.strip()        
        print(file_name)
        Picture(pic_md5 = file_name)
        #Sender = S.bind(ctx)
        #Sender.image(file_name, type=S.TYPE_PATH)


receive_group_msg=receive_friend_msg=main
