from botoy import logger, MsgTypes, S, GroupMsg, FriendMsg
from botoy.sugar import Picture, Text, Voice
from botoy.parser import friend, group
from botoy.decorators import ignore_botself
from botoy.session import SessionHandler, session, FILTER_SUCCESS
import httpx
import time
import os
from PIL import Image

__doc__ = """图片存储助手"""


def session_filter(ctx):
    if ctx.Content == "倒放":
        return FILTER_SUCCESS

cur_file_dir = os.path.dirname(os.path.realpath(__file__))
l_session = SessionHandler(ignore_botself, session_filter, single_user=True, expiration = 50)


@l_session.parse
def _par(ctx):
    if ctx.MsgType != MsgTypes.PicMsg:
        return None

    url = None

    if isinstance(ctx, FriendMsg):
        pics = friend.pic(ctx)
        url = pics.FriendPic[0].Url
    elif isinstance(ctx, GroupMsg):
        pics = group.pic(ctx)
        url = pics.GroupPic[0].Url

    return url


def find_imgtype(type_str):
    prefix = 'image/'
    img_type = None
    index = type_str.find(prefix)
    if index == 0:
        img_type = type_str[len(prefix):]
    return img_type


@l_session.handle
def _h():
    session.send_text('指令已收到，请发送要倒放的图片')

    timeout = session._expiration
    last = time.monotonic()
    while True:
        if time.monotonic() - last > timeout:
            session.send_text('因对方无响应，会话关闭')
            l_session.finish()
            break
        pic_url = session.pop('pic_url', wait = True, timeout=1)
        if not pic_url:
            continue

        if download_gif(pic_url):
            reverse_gif()
            Picture(pic_path=os.path.join(cur_file_dir, 'reversed.gif'))

        else:
            session.send_text('下载图片失败')


def download_gif(pic_url):
    try:
        res = httpx.get(pic_url)
        res.raise_for_status()
        img_type = find_imgtype(res.headers['content-type'])
        if not img_type:
            raise Exception('Failed to resolve image type')
        if img_type.upper() != "GIF":
            return False
        file_name = 'to_reverse.gif'
        file_path = os.path.join(cur_file_dir, file_name)
        logger.info('Saving image to: {}'.format(file_path))
        with open(file_path, 'wb') as img:
            img.write(res.content)
        return True
    except Exception as e:
        logger.warning('Failed to get picture from url:{},{}'.format(pic_url, e))
        return False

    return False


def reverse_gif():
    im = Image.open(os.path.join(cur_file_dir, 'to_reverse.gif'))
    frames = im.get_frames()
    frames.reverse()
    frames[0].save(os.path.join(cur_file_dir, 'reversed.gif'), save_all=True, append_images=frames[1:])

@ignore_botself
def main(ctx):
    l_session.message_receiver(ctx)

receive_group_msg=receive_friend_msg=main
