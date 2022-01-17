import json
import os, random
from botoy import logger, GroupMsg, FriendMsg
from botoy.sugar import Picture, Text
import httpx
import re

from .cmd_dbi import cmdDB, cmdInfo, replyInfo, aliasInfo, CMD_TYPE


class PicObj():
    user: str
    Url: str
    Md5: str


cur_file_dir = os.path.dirname(os.path.realpath(__file__))
pic_dir = ''
try:
    with open(cur_file_dir + '/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        pic_dir = config['pic_dir']
except:
    logger.error('config error')
    raise


class REPLY_TYPE:
    PIC_MD5 = 1
    PIC_PATH = 2
    TEXT = 3


class reply_server:

    def __init__(self):
        self.db = cmdDB()
        self.cmd_info = cmdInfo()
        self.cur_dir = ''
        self.reply = ""
        self.reply_type = 0
        self.user_id = ""
        
    def checkout(self, cmd, cmd_type=0, create=False):
        real_cmd_id = self.db.get_real_cmd(cmd)  #handle alias
        self.cmd_info = self.db.get_cmd_info(cmd_id=real_cmd_id)
        self.cur_dir = os.path.join(pic_dir, self.cmd_info.cmd)
        if not self.cmd_info:
            if create:
                if not os.path.exists(self.cur_dir) and cmd_type == CMD_TYPE.PIC:
                    os.mkdir(self.cur_dir )
                self.db.add_cmd(cmd, cmd_type)
                self.db.add_alias(cmd, 0)
                self.cmd_info = self.db.get_cmd_info(cmd)
            else:
                return False

        if self.cmd_info.active == 0:
            return False

        return True

    def handle_save_cmd(self, cmd):
        logger.debug('saving {}'.format(cmd))
        if re.match("^pic.{1,}", cmd):  # should be handled by session
            return
        elif re.match("^txt.{1,}", cmd):  # save TEXT reply
            return self.save_text_reply(cmd[3:])
        elif re.match("^ftxt.{1,}", cmd):  # save format TEXT reply
            return self.save_ftext_reply(cmd[4:])
        elif re.match("^alias.{1,}", cmd):  # save alias
            return self.save_alias(cmd[5:])

    def handle_cmd(self, ctx):
        self.reply_type = 0
        self.reply = ""

        if isinstance(ctx, FriendMsg):
            self.user_id = ctx.FromUin
        elif isinstance(ctx, GroupMsg):
            self.user_id = ctx.FromUserId

        if re.match("^_save.{1,}", ctx.Content):
            return self.handle_save_cmd(ctx.Content[5:])

        arg = ""
        checkout_good = False
        content = ctx.Content.strip()
        if len(content) > 1:
            re.sub("[!?\uff1f\uff01]$", '', content)

        space_index = content.find(' ')
        if space_index == -1:
            checkout_good = self.checkout(content)
        else:
            cmd = content[0:space_index]
            checkout_good = self.checkout(cmd)
            arg = content[space_index:]
            arg = arg.strip()
        if not checkout_good:
            return

        msg_type = self.cmd_info.type
        if msg_type == CMD_TYPE.PIC:
            self.random_pic_path(arg)
        elif msg_type == CMD_TYPE.TEXT_TAG or msg_type == CMD_TYPE.TEXT_FORMAT:
            self.random_reply(arg)

    def random_reply(self, arg):
        reply_info = None
        if self.cmd_info.type == CMD_TYPE.TEXT_TAG and len(arg):
            reply_info = self.db.get_reply_by_tag(self.cmd_info.cmd_id, arg)
        else:
            random_lim = 5
            reply_id = 0
            while not reply_info:
                random_lim -= 1
                if random_lim == 0:
                    break
                reply_id = random.randint(1, self.cmd_info.sequence)
                logger.debug('getting with{}:{}'.format(self.cmd_info.cmd_id, reply_id))
                reply_info = self.db.get_reply(self.cmd_info.cmd_id, reply_id)

        if reply_info and self.cmd_info.type == CMD_TYPE.TEXT_FORMAT and reply_info.has_arg:
            reply_info.reply = reply_info.reply.format(arg)
        if reply_info:
            logger.debug("inc{},{}".format(reply_info.cmd_id, reply_info.reply_id))
            self.db.used_inc(reply_info.cmd_id, reply_info.reply_id)
            self.reply = reply_info.reply
            self.reply_type = REPLY_TYPE.TEXT

    def random_pic(self, tag):
        if self.cmd_info.sequence == 0:
            return None
        
        random_lim = 5
        pic_info = None
        pic_id = 0
        while not pic_info:
            random_lim -= 1
            if random_lim == 0:
                break
            pic_id = random.randint(1, self.cmd_info.sequence)
            logger.debug('getting with{}:{}'.format(self.cmd_info.cmd_id, pic_id))
            pic_info = self.db.get_pic(self.cmd_info.cmd_id, pic_id)

        if pic_info and pic_id:
            self.db.used_inc(self.cmd_info.cmd_id, pic_id)

        return pic_info

    def random_pic_md5(self, tag):
        pic_info = self.random_pic(tag)
        if pic_info:
            self.reply=pic_info.md5
            self.reply_type = REPLY_TYPE.PIC_MD5

    def random_pic_path(self, tag):
        pic_info = self.random_pic(tag)
        if pic_info:
            file_name = '{}.{}'.format(pic_info.md5, pic_info.file_type)
            file_name = file_name.replace('/', 'SLASH') #avoid path revolving issue
            file_name = os.path.join(self.cur_dir,file_name)
            self.reply=file_name
            self.reply_type = REPLY_TYPE.PIC_PATH

    @staticmethod
    def find_imgtype(type_str):
        prefix = 'image/'
        img_type = None
        index = type_str.find(prefix)
        if index == 0:
            img_type = type_str[len(prefix):]
        return img_type

    def save_pic(self, pic: PicObj, tag="", reply=""):

        if pic.Url:
            try:
                res = httpx.get(pic.Url)
                res.raise_for_status()
                img_type = self.find_imgtype(res.headers['content-type'])
                if not img_type:
                    raise Exception('Failed to resolve image type')
                self.cmd_info.sequence += 1;
                file_name = '{}.{}'.format(pic.Md5, img_type)
                file_name = file_name.replace('/', 'SLASH') #avoid path revolving issue
                file_path = os.path.join(self.cur_dir, file_name)
                logger.warning('Saving image to: {}'.format(file_path))
                with open(file_path, 'wb') as img:
                    img.write(res.content)
                self.db.add_pic(self.cmd_info.cmd_id, self.cmd_info.sequence, pic.Md5, img_type, CMD_TYPE.PIC, user_id=pic.user)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, self.cmd_info.sequence)
                return True
            except Exception as e:
                logger.warning('Failed to get picture from url:{},{}'.format(pic.Url, e))
                raise
        
        return False

    @staticmethod
    def save_cmd_parse(cmd):
        cmd = cmd.strip()
        arg = ""
        reply = ""
        space_index = cmd.find(' ')
        if space_index > 0:
            arg = cmd[space_index:]
            cmd = cmd[0:space_index]
        else:
            return cmd, None, None

        space_index = arg.find(' reply:')
        if space_index >= 0:
            reply = arg[space_index+7:]
            arg = arg[0:space_index]
            arg = arg.strip()

        return cmd, arg, reply

    def save_text_reply(self, cmd):
        logger.debug('saving {}'.format(cmd))
        cmd, tag, reply = self.save_cmd_parse(cmd)
        if len(cmd) and len(reply):
            if self.checkout(cmd, cmd_type=CMD_TYPE.TEXT_TAG, create=True):
                self.cmd_info.sequence += 1
                self.db.add_reply(self.cmd_info.cmd_id, self.cmd_info.sequence, has_arg=0, tag=tag, type=CMD_TYPE.TEXT_TAG,reply=reply, user_id=self.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, self.cmd_info.sequence)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "回复存储成功，{}({}):{}".format(cmd,tag,reply)

    def save_ftext_reply(self, cmd):
        cmd, arg, reply = self.save_cmd_parse(cmd)
        if len(cmd) and len(reply):
            if self.checkout(cmd, cmd_type=CMD_TYPE.TEXT_FORMAT, create=True):
                self.cmd_info.sequence += 1
                self.db.add_reply(self.cmd_info.cmd_id, self.cmd_info.sequence, has_arg=1, tag="", type=CMD_TYPE.TEXT_FORMAT,reply=reply, user_id=self.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, self.cmd_info.sequence)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "定形回复存储成功，{}({}):{}".format(cmd,arg,reply)

    def save_alias(self, cmd):
        space_index = cmd.find(' ')
        if space_index > 0:
            p_cmd = cmd[space_index+1:]
            p_cmd = p_cmd.strip()
            cmd = cmd[0:space_index]
            if self.checkout(p_cmd):
                self.db.add_alias(cmd, self.cmd_info.cmd_id)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "alias设置成功:{} to {}".format(cmd, p_cmd)





