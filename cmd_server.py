import json
import os, random
from botoy import logger, GroupMsg, FriendMsg
import httpx
import re

from .cmd_dbi import cmdDB, cmdInfo, replyInfo, CMD_TYPE


class PicObj:
    user: str
    Url: str
    Md5: str


cur_file_dir = os.path.dirname(os.path.realpath(__file__))
pic_dir = ""
super_user = ""
try:
    with open(cur_file_dir + '/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        pic_dir = config['pic_dir']
        super_user = config["super_user"]
except:
    logger.error('config error')
    raise


g_user_cache = {}
g_app_cache = {}


class REPLY_TYPE:
    PIC_MD5 = 1
    PIC_PATH = 2
    TEXT = 3


CMD_TYPE_LIST = [CMD_TYPE.PIC, CMD_TYPE.TEXT_TAG, CMD_TYPE.TEXT_FORMAT, CMD_TYPE.VOICE]


class Selector:
    def __init__(self):
        self.candies = []
        self.weights = []
        self.last_wei = 0

    def add(self, cand, wei):
        self.candies.append(cand)
        self.last_wei += wei
        self.weights.append(self.last_wei)

    def shuffle(self):
        if len(self.candies) == 0:
            return None

        result = random.randint(1, self.last_wei)
        index = 0
        while index < len(self.candies):
            if result <= self.weights[index]:
                break
            index += 1 

        return self.candies[index]


class reply_server:

    def __init__(self):
        self.db = cmdDB()
        self.cmd_info = cmdInfo()
        self.cur_dir = ''
        self.reply = ""
        self.reply2 = ""
        self.reply_type = 0
        self.user_info = None
        self.use_md5 = 0

    def get_user(self, user_qq):
        if user_qq in g_user_cache:
            self.user_info = g_user_cache[user_qq]
            logger.debug("用户：{} id：{} perm: {}".format(user_qq, self.user_info.user_id, self.user_info.permission))
        else:
            self.user_info = self.db.get_user(user_qq)
            if self.user_info:
                g_user_cache[user_qq] = self.user_info
            else:
                self.db.add_user(user_qq)
                self.user_info = self.db.get_user(user_qq)
                if self.user_info:
                    g_user_cache[user_qq] = self.user_info
                else:
                    return False

        return True
        

    def checkout(self, cmd: str, user_qq: str, cmd_type=0, create=False):

        self.cmd_info = self.db.get_real_cmd(cmd)  # handle alias

        if self.cmd_info:
            self.cur_dir = os.path.join(pic_dir, self.cmd_info.cmd)
        else:
            self.cur_dir = os.path.join(pic_dir, cmd)

        if not self.cmd_info:
            if create:
                if not os.path.exists(self.cur_dir) and (cmd_type & CMD_TYPE.PIC):
                    os.mkdir(self.cur_dir)
                cmd_id = self.db.add_alias(cmd, 0, cmd_type, 0)
                self.cmd_info = self.db.get_real_cmd(cmd)
            else:
                return False

        if not self.get_user(user_qq):
            return False
        if self.cmd_info.active == 0 or self.user_info.permission < self.cmd_info.level:
            return False

        return True

    def set_cmd_type(self, cmd, arg):
        if arg is None:
            return
        if self.checkout(cmd, super_user):
            cmd_type = int(arg.strip())
            if not os.path.exists(self.cur_dir) and (cmd_type & CMD_TYPE.PIC):
                os.mkdir(self.cur_dir)
            self.db.set_cmd_type(self.cmd_info.cmd_id, cmd_type)
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = "{}类型变为:{}".format(cmd, cmd_type)

    def handle_save_cmd(self, cmd, user_qq):
        logger.debug('saving {}'.format(cmd))
        if re.match("^pic.{1,}", cmd):  # should be handled by session
            return
        elif re.match("^txt.{1,}", cmd):  # save TEXT reply
            return self.save_text_reply(cmd[3:], user_qq)
        elif re.match("^ftxt.{1,}", cmd):  # save format TEXT reply
            return self.save_ftext_reply(cmd[4:], user_qq)
        elif re.match("^alias.{1,}", cmd):  # save alias
            return self.save_alias(cmd[5:])

    def handle_set_cmd(self, cmd):
        if re.match("^md5", cmd):
            if len(cmd) > 3:
                self.use_md5 = 0
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "md5 off"
            else:
                self.use_md5 = 1
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "md5 on"
        if re.match("^type", cmd):
            cmd, arg = self.get_next_arg(cmd)
            self.set_cmd_type(cmd[4:], arg)

    def handle_cmd(self, ctx):
        self.reply_type = 0
        self.reply = ""
        user_qq = ""
        if isinstance(ctx, FriendMsg):
            user_qq = str(ctx.FromUin)
        elif isinstance(ctx, GroupMsg):
            user_qq = str(ctx.FromUserId)

        if re.match("^_save.{1,}", ctx.Content):
            return self.handle_save_cmd(ctx.Content[5:], user_qq)
        elif re.match("^_set.{1,}", ctx.Content):
            return self.handle_set_cmd(ctx.Content[4:])
        
        arg = ""
        checkout_good = False
        content = ctx.Content.strip()
        if len(content) > 1:
            content = re.sub("[!?\uff1f\uff01]$", '', content)  # erase ! ? at end of content

        space_index = content.find(' ')
        if space_index == -1:
            checkout_good = self.checkout(content, user_qq)
        else:
            cmd = content[0:space_index]
            checkout_good = self.checkout(cmd, user_qq)
            arg = content[space_index:]
            arg = arg.strip()
        if not checkout_good:
            return

        return self.random_reply(arg)

    def random_reply(self, arg):
        reply_info = None
        if len(arg):
            if ((CMD_TYPE.TEXT_FORMAT & self.cmd_info.cmd_type) and
                    self.cmd_info.sequences[CMD_TYPE.TEXT_FORMAT] > 0):
                return self.random_ftext(arg)
            elif ((CMD_TYPE.PIC & self.cmd_info.cmd_type) and
                    self.cmd_info.sequences[CMD_TYPE.PIC] > 0):
                return self.random_pic(arg)

        cmd_selector = Selector()
        for cmd_type in CMD_TYPE_LIST:
            if cmd_type & self.cmd_info.cmd_type and self.cmd_info.sequences[cmd_type] > 0:
                cmd_selector.add(cmd_type, self.cmd_info.sequences[cmd_type])
        cmd_type = cmd_selector.shuffle()

        if cmd_type == CMD_TYPE.TEXT_TAG:
            self.random_text(arg)
        elif cmd_type == CMD_TYPE.TEXT_FORMAT:
            self.random_ftext(arg)
        elif cmd_type == CMD_TYPE.PIC:
            self.random_pic(arg)

    def random_text(self, tag):
        reply_info = None
        if len(tag):
            reply_info = self.db.get_reply_by_tag(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, tag)
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.TEXT_TAG])
            reply_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, reply_id)

        if reply_info:
            self.reply = reply_info.reply
            self.reply_type = REPLY_TYPE.TEXT
            self.db.used_inc(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                             CMD_TYPE.TEXT_TAG, reply_info.reply_id )

    def random_ftext(self, arg):
        reply_info = None
        if len(arg) == 0:
            return
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.TEXT_FORMAT])
            reply_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_FORMAT, reply_id)

        if reply_info:
            self.reply = reply_info.reply.format(arg)
            self.reply_type = REPLY_TYPE.TEXT
            self.db.used_inc(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                             CMD_TYPE.TEXT_FORMAT, reply_info.reply_id)

    def _random_pic(self, tag) -> replyInfo:
        reply_info = None
        if len(tag):
            reply_info = self.db.get_reply_by_tag(self.cmd_info.cmd_id, CMD_TYPE.PIC, tag)
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.PIC])
            reply_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.PIC, reply_id)
            if reply_info:
                self.db.used_inc(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                                 CMD_TYPE.PIC, reply_info.reply_id)

        return reply_info

    def random_pic(self, arg):
        if self.use_md5:
            self.random_pic_md5(arg)
        else:
            self.random_pic_path(arg)

    def random_pic_md5(self, tag):
        pic_info = self._random_pic(tag)
        if pic_info:
            self.reply=pic_info.md5
            self.reply_type = REPLY_TYPE.PIC_MD5

    def random_pic_path(self, tag):
        pic_info = self._random_pic(tag)
        if pic_info:
            file_name = '{}.{}'.format(pic_info.md5, pic_info.file_type)
            file_name = file_name.replace('/', 'SLASH')  # avoid path revolving issue
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
                file_name = '{}.{}'.format(pic.Md5, img_type)
                file_name = file_name.replace('/', 'SLASH')  # avoid path revolving issue
                file_path = os.path.join(self.cur_dir, file_name)
                logger.warning('Saving image to: {}'.format(file_path))
                with open(file_path, 'wb') as img:
                    img.write(res.content)
                self.cmd_info.sequences[CMD_TYPE.PIC] += 1
                new_reply_id = self.cmd_info.sequences[CMD_TYPE.PIC]
                self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.PIC, new_reply_id, tag=tag, md5=pic.Md5, file_type=img_type, reply=reply, user_id=self.user_info.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.PIC, new_reply_id)
                return True
            except Exception as e:
                logger.warning('Failed to get picture from url:{},{}'.format(pic.Url, e))
                raise
        
        return False

    @staticmethod
    def get_next_arg(cmd):
        space_index = cmd.find(' ')
        if space_index > 0:
            return cmd[0:space_index], cmd[space_index:]
        else:
            return cmd, None

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

    def save_text_reply(self, cmd, user_qq):
        logger.debug('saving {}'.format(cmd))
        cmd, tag, reply = self.save_cmd_parse(cmd)
        if len(cmd) and len(reply):
            if self.checkout(cmd, user_qq, cmd_type=CMD_TYPE.TEXT_TAG, create=True):
                new_reply_id = self.cmd_info.sequences[CMD_TYPE.TEXT_TAG] + 1
                self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, new_reply_id, tag=tag, reply=reply, user_id=self.user_info.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, new_reply_id)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "回复存储成功，{}({}):{}".format(cmd, tag, reply)

    def save_ftext_reply(self, cmd, user_qq):
        cmd, arg, reply = self.save_cmd_parse(cmd)
        if len(cmd) and len(reply):
            if self.checkout(cmd, user_qq, cmd_type=CMD_TYPE.TEXT_FORMAT, create=True):
                new_reply_id = self.cmd_info.sequences[CMD_TYPE.TEXT_FORMAT] + 1
                self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_FORMAT, new_reply_id, reply=reply, user_id=self.user_info.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.TEXT_FORMAT, new_reply_id)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "定形回复存储成功，{}({}):{}".format(cmd,arg,reply)

    def save_alias(self, cmd):
        space_index = cmd.find(' ')
        if space_index > 0:
            p_cmd = cmd[space_index+1:]
            p_cmd = p_cmd.strip()
            cmd = cmd[0:space_index]
            if self.checkout(p_cmd, super_user):
                self.db.add_alias(cmd, self.cmd_info.cmd_id, 0, 0)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "alias设置成功:{} to {}".format(cmd, p_cmd)

    def app_usage(self, app: str, user_qq):
        if self.checkout(app, user_qq, create=True, cmd_type=1000):
            self.db.used_inc(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                             1000, 1)









