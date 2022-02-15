import json
import os
import random
import time

from botoy import logger, GroupMsg, FriendMsg, jconfig, Action, MsgTypes
from botoy.parser import group, friend
from botoy.utils import file_to_base64
import httpx
import re
import queue
from typing import Union

from .cmd_dbi import cmdDB, cmdInfo, replyInfo, CMD_TYPE, userInfo, groupInfo
from .exceptions import *


# build-in cmd definition:

class PicObj:
    user: str
    Url: str
    Md5: str
    cmd: str
    tag: str
    reply: str
    private: bool

    def __init__(self):
        self.user = ""
        self.Url = ""
        self.Md5 = ""
        self.cmd = ""
        self.tag = ""
        self.reply = ""


cur_file_dir = os.path.dirname(os.path.realpath(__file__))
pic_dir = ""
super_user = ""
user_record_level = 2
# user_record_level:
# 0: do not record
# 1: cmd level record
# 2: reply_level_record
bot_primary_cmd = "FUFU"  # bot的主题图库, 用于在_listcmd时挑选显示的图片

try:
    with open(cur_file_dir + '/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        pic_dir = config['pic_dir']
        voice_dir = config['voice_dir']
        super_user = config["super_user"]
        if "user_record_level" in config:
            user_record_level = super_user = config["user_record_level"]
except:
    logger.error('config error')
    raise

g_user_cache = {}
g_group_cache = {}


class REPLY_TYPE:
    PIC_MD5 = 1
    PIC_PATH = 2
    TEXT = 3
    VOICE = 4


CMD_TYPE_LIST = [CMD_TYPE.PIC, CMD_TYPE.TEXT_TAG, CMD_TYPE.TEXT_FORMAT, CMD_TYPE.VOICE]


# user id getter with cache
def get_user(user_qq):
    user_info = None
    if user_qq in g_user_cache:
        user_info = g_user_cache[user_qq]
        logger.debug("Cached qq：{} id：{} perm: {}".format(user_qq, user_info.user_id, user_info.permission))
    else:
        db = cmdDB()
        user_info = db.get_user(user_qq)
        if user_info:
            g_user_cache[user_qq] = user_info
        else:
            db.add_user(user_qq)
            user_info = db.get_user(user_qq)
            if user_info:
                g_user_cache[user_qq] = user_info

    return user_info


# group id getter with cache
def get_group(group_qq: str):
    group_info = None
    if group_qq in g_group_cache:
        group_info = g_group_cache[group_qq]
        logger.debug("get cached group_info qq:{}, enable:{}".format(group_qq, group_info.enable))
    else:
        db = cmdDB()
        group_info = db.get_group(group_qq)
        if group_info:
            g_group_cache[group_qq] = group_info
        else:
            db.add_group(group_qq)
            group_info = db.get_group(group_qq)
            if group_info:
                g_group_cache[group_qq] = group_info

    return group_info


# A random shuffler with weight
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

    def __init__(self, async_server=True):
        self.db = cmdDB(use_regexp=True)
        self.cmd_info = cmdInfo()
        self.cur_dir = ""
        self.reply = ""  # 存储文字回复/图片MD5/路径
        self.reply2 = ""  # 存储图片附带回复
        self.reply_type = 0
        self.user_info = None
        self.use_md5 = 1  # 图片回复使用MD5
        self.group_flag = True  # 群聊上下文
        self.reply_at = 0  # 回复时@的qq
        self.running = False  # 异步模式下的状态
        if not async_server:  # 不以异步模式运行时
            self.cmd_queue = None
            self.action = None
        else:
            self.cmd_queue = queue.Queue()
            self.action = Action(jconfig.bot, host=jconfig.host, port=jconfig.port)

    def help(self, group_id: str):
        cmds = self.db.get_all_cmd(CMD_TYPE.PLUGIN)
        p_mgr = plugin_manager()
        help_content = "本群已启用功能:\n"
        content_off = "\n------------\n以下功能已禁用:\n"
        off = False
        for cmd in cmds:
            if cmd.active:
                if p_mgr.checkout(group_qq_s=group_id, cmd_id=cmd.cmd_id):
                    help_content += f"\u26aa {cmd.cmd}\n"
                else:
                    off = True
                    content_off += f"\u2716 {cmd.cmd}\n"

        help_content += "输入 【帮助+功能】 查看各功能详情"
        if off:
            help_content += content_off
        self.reply_type = REPLY_TYPE.TEXT
        self.reply = help_content

    def reply_super(self, reply: str):
        self.action.sendFriendText(int(super_user), reply)

    def check_admin(self, user_qq):
        if user_qq == super_user:
            return True
        else:
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = "主人说不可以听陌生人的话捏"
            return False

    def enqueue(self, ctx: Union[GroupMsg, FriendMsg]):
        if self.cmd_queue and (isinstance(ctx, FriendMsg) or isinstance(ctx, GroupMsg)):
            self.cmd_queue.put(ctx)

    def wait_for_msg(self):
        self.running = True
        while self.cmd_queue and self.running:
            if not self.cmd_queue.empty():
                ctx = self.cmd_queue.get()
                try:
                    self.handle_cmd(ctx)
                except CmdLimitExceedException or ReplyLimitExceedException or CmdLengthExceedException or CmdWithRegExpException:
                    logger.warning("limit exceed exception")
                self.handle_reply(ctx)
                time.sleep(0.3)
            else:
                time.sleep(1)

    def handle_reply(self, ctx: Union[GroupMsg, FriendMsg]):
        if self.action and self.reply_type:
            if self.group_flag:
                if self.reply_type == REPLY_TYPE.PIC_MD5:
                    self.action.sendGroupPic(ctx.FromGroupId, content=self.reply2, picMd5s=self.reply)
                elif self.reply_type == REPLY_TYPE.PIC_PATH:
                    self.action.sendGroupPic(ctx.FromGroupId, content=self.reply2,
                                             picBase64Buf=file_to_base64(self.reply))
                elif self.reply_type == REPLY_TYPE.TEXT:
                    self.action.sendGroupText(ctx.FromGroupId, content=self.reply, atUser=self.reply_at)
                elif self.reply_type == REPLY_TYPE.VOICE:
                    self.action.sendGroupVoice(ctx.FromGroupId, voiceBase64Buf=file_to_base64(self.reply))

    def handle_cmd(self, ctx):
        self.reply_at = 0
        self.reply_type = 0
        self.reply = ""
        user_qq = ""
        group_qq = ""

        if isinstance(ctx, FriendMsg):
            user_qq = str(ctx.FromUin)
            self.group_flag = False
        elif isinstance(ctx, GroupMsg):
            user_qq = str(ctx.FromUserId)
            group_qq = str(ctx.FromGroupId)
            self.group_flag = True

        if ctx.MsgType == MsgTypes.PicMsg:
            pic_obj = self.parse_pic(ctx)
            if len(pic_obj.cmd):
                self.save_pic(pic_obj)
            return

        target = None
        flag_at_me = False
        if ctx.MsgType == "AtMsg":
            target = ctx.target[0]
            if target == jconfig.bot:
                flag_at_me = True

        if ctx.Content == "帮助":
            self.help(group_qq)
        elif ctx.Content == "_listcmd":
            return self.list_all_cmd(user_qq)
        elif ctx.Content == "_scanvoice":
            return self.scan_voice_dir()
        elif re.match("^_save.{1,}", ctx.Content):
            return self.handle_save_cmd(ctx.Content[5:], user_qq)
        elif re.match("^_set.{1,}", ctx.Content):
            return self.handle_set_cmd(ctx.Content[4:], user_qq, target)
        elif re.match("^_disable.{1,}", ctx.Content):
            return self.set_cmd_active(ctx.Content[8:], 0, user_qq, group_qq)
        elif re.match("^_enable.{1,}", ctx.Content):
            return self.set_cmd_active(ctx.Content[7:], 1, user_qq, group_qq)
        elif re.match("^_check.{1,}", ctx.Content):
            return self.handle_check_cmd(ctx.Content[6:], user_qq)
        elif re.match("^_rename.{1,}", ctx.Content):
            return self.rename_cmd(ctx.Content[7:], user_qq)

        arg = ""
        checkout_good = False
        content = ctx.Content.strip()
        if len(content) > 1:
            content = re.sub("[!?\uff1f\uff01]$", '', content)  # erase ! ? at end of content
        pic_flag = False

        space_index = content.find(' ')  # 附带参数的关键词
        if space_index == -1:
            checkout_good = self.checkout(content, user_qq, private=flag_at_me, full=False)
        else:
            cmd = content[0:space_index]
            checkout_good = self.checkout(cmd, user_qq)
            arg = content[space_index:]
            arg = arg.strip()
        if not checkout_good:
            return

        if flag_at_me:
            self.reply_at = int(user_qq)
            return self.handle_private_cmd()

        return self.random_reply(arg)

    def cmd_check(self, cmd):
        if len(cmd) > 15:
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = "【系统错误: 关键词长度不能大于15个字符!】"
            raise CmdLengthExceedException

        if re.match("[\^*$+|]+", cmd):
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = "【系统错误: 非法关键词！关键词疑似包含正则表达式】"
            raise CmdLengthWithRegExpException

    def checkout(self, cmd: str, user_qq: str, cmd_type=0, create=False, check_active=True, private=False, full=True):
        # 关键词检索函数, 或是新建关键词, 成功的话会对self.cmd_info赋值
        # cmd: 关键词
        # user_qq: 发送关键词的qq号
        # cmd_type: 创建新关键词(或新类型回复)的类型
        # create: 关键词不存在的话是否创建
        # check: 是否检查active
        # private: 是否为私人关键词检索

        self.user_info = get_user(user_qq)
        if not self.user_info:
            return False

        cmd = cmd.upper()  # cmd is case-insensitive
        if create:
            self.cmd_check(cmd)

        if private:
            self.cmd_info = self.db.get_private_cmd(self.user_info.user_id, cmd, real=True)
        else:
            self.cmd_info = self.db.get_cmd(cmd, real=True, full=full)  # alias is handled inside

        if self.cmd_info:
            if private:
                self.cur_dir = os.path.join(pic_dir, f"_{user_qq}", self.cmd_info.cmd)
            else:
                self.cur_dir = os.path.join(pic_dir, self.cmd_info.cmd)
        elif create:
            if private:
                self.cur_dir = os.path.join(pic_dir, f"_{user_qq}", cmd)
            else:
                self.cur_dir = os.path.join(pic_dir, cmd)

        if create and not os.path.exists(self.cur_dir) and (cmd_type & CMD_TYPE.PIC):
            os.makedirs(self.cur_dir, exist_ok=True)

        if not self.cmd_info:

            if create:
                self.cmd_info = self.add_alias(cmd, 0, cmd_type, 0, private)

        if create and cmd_type & self.cmd_info.cmd_type == 0:
            self.db.set_cmd_type(self.cmd_info.cmd_id, cmd_type | self.cmd_info.cmd_type)

        if not self.cmd_info:
            return False

        # Availability check
        if (check_active and self.cmd_info.active == 0) or self.user_info.permission < self.cmd_info.level:
            return False

        return True

    def add_alias(self, cmd, parent, reply_type, level, private=False):
        # 这里不会检查alias是否已经存在, 请在调用处检查
        if not private:  # Public cmd alias
            return self.db.add_alias(cmd, parent, reply_type, level)
        else:
            max_id = self.db.get_private_cmd_max_id(self.user_info.user_id)
            count = self.db.get_private_cmd_count(self.user_info.user_id)
            if count >= self.user_info.private_limit:  # assume the user_info has been retrieved here
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "【系统错误: 私人关键词超过上限了！】"
                raise CmdLimitExceedException
            else:
                return self.db.add_private_alias(self.user_info.user_id, max_id + 1, cmd, parent)

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

    def set_cmd_active(self, cmd, active, user_qq: str, group_qq: str):
        if not self.check_admin(user_qq):
            return
        self.reply_type = REPLY_TYPE.TEXT
        if self.checkout(cmd, user_qq, check_active=False):
            if self.cmd_info.cmd_type == CMD_TYPE.PLUGIN and group_qq != "":
                group_info = get_group(group_qq)
                self.db.set_group_cmd_status(group_info.group_id, self.cmd_info.cmd_id, active)
                if active == 0:
                    self.reply = "群功能【{}】已禁用".format(cmd)
                else:
                    self.reply = "群功能【{}】已启用".format(cmd)
            else:
                self.db.set_cmd_active(cmd, self.cmd_info.cmd_id, active)
                if active == 0:
                    self.reply = "关键词【{}】已禁用".format(cmd)
                else:
                    self.reply = "关键词【{}】已启用".format(cmd)
        else:
            self.reply = "关键词【{}】不存在".format(cmd)

    def set_cmd_level(self, cmd, level):
        if cmd and level:
            level = int(level)
            if self.checkout(cmd, super_user):
                self.db.set_cmd_level(self.cmd_info.cmd_id, level)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "关键词【{}】，等级已修改为【{}】".format(cmd, level)
            else:
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "找不到关键词【{}】捏".format(cmd)

    def set_permission(self, target_qq, permission):
        if not target_qq:
            target_qq = super_user
        if not permission:
            return

        user_info = get_user(target_qq)
        if user_info:
            permission = int(permission)
            self.db.set_user_permission(user_info.user_id, permission)
            g_user_cache[target_qq].permission = permission
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = "用户【{}】，权限已修改为【{}】".format(target_qq, permission)

    def rename_cmd(self, cmd, user_qq):
        if not self.check_admin(user_qq):
            return
        cmd, arg = self.get_next_arg(cmd)
        if self.checkout(cmd, user_qq, check_active=False):
            if not self.db.get_cmd(arg):  # check if to arg already exists
                self.db.rename_cmd(self.cmd_info.cmd_id, arg)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "重命名关键词【{}】->关键词【{}】".format(cmd, arg)
            else:
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "关键词【{}】已存在，无法重命名".format(arg)
        else:
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = "关键词【{}】不存在".format(cmd)

    def list_all_cmd(self, user_qq):
        output_text = ""
        output_list = {}
        self.user_info = get_user(user_qq)
        if self.user_info:
            cmds = self.db.get_all_cmd()
            if cmds is None:
                return
            for cmd in cmds:
                if cmd.active and cmd.level < self.user_info.permission:
                    if cmd.orig_id == 0:
                        out_str = cmd.cmd
                        if self.user_info.permission > 50:  # 权限大于一定值显示每项关键词的回复数量
                            if CMD_TYPE.PIC & cmd.cmd_type and cmd.sequences[CMD_TYPE.PIC]:
                                out_str += " 图片回复{}项".format(cmd.sequences[CMD_TYPE.PIC])
                            if CMD_TYPE.TEXT_TAG & cmd.cmd_type and cmd.sequences[CMD_TYPE.TEXT_TAG]:
                                out_str += " 文字回复A类{}项".format(cmd.sequences[CMD_TYPE.TEXT_TAG])
                            if CMD_TYPE.TEXT_FORMAT & cmd.cmd_type and cmd.sequences[CMD_TYPE.TEXT_FORMAT]:
                                out_str += " 文字回复B类{}项".format(cmd.sequences[CMD_TYPE.TEXT_FORMAT])
                            if CMD_TYPE.VOICE & cmd.cmd_type and cmd.sequences[CMD_TYPE.VOICE]:
                                out_str += " 语音回复{}项".format(cmd.sequences[CMD_TYPE.VOICE])

                        output_list[cmd.cmd_id] = out_str
                    else:  # 处理同义词
                        parent_id = 0
                        if cmd.orig_id in output_list:
                            parent_id = cmd.orig_id
                        else:
                            cmd_tmp = cmd
                            while True:
                                parent_id = 0
                                for cmd_p in cmds:
                                    if cmd_p.cmd_id == cmd_tmp.orig_id:
                                        cmd_tmp = cmd_p
                                        if cmd_tmp.orig_id == 0:
                                            parent_id = cmd_tmp.cmd_id
                                        else:
                                            parent_id = -1
                                        break
                                if parent_id >= 0:
                                    break

                        if parent_id in output_list:
                            output_list[parent_id] += "({})".format(cmd.cmd)
            for value in output_list.values():
                if len(value):
                    output_text += value + "\n"

            if len(output_text):
                template = "欢迎使用调教助手，你的可用关键词:\n{}【调教方法】\n发送【_savepic关键词 tag(可选) reply回复（可选）】开启图片存储会话\n发送【_savetxt关键词 tag(可选) reply回复】存储文字回复\n发送【_savealias子关键词 父关键词】建立同义词关联\n语音调教暂时不支持使用~\n例:\n_savepic色色\n_savetxt我想色色 reply不许色色！ (reply前有空格)\n_savealias我要色色 我想色色\n注意不要教我奇怪的东西哦~[PICFLAG]"
                if self.checkout(bot_primary_cmd, user_qq):
                    self.random_pic("")
                self.reply2 = template.format(output_text)

    def handle_save_cmd(self, cmd, user_qq):
        logger.info('saving {}'.format(cmd))
        if re.match("^pic.{1,}", cmd):  # should be handled by session
            return
        elif re.match("^txt.{1,}", cmd):  # save TEXT reply
            return self.save_text_reply(cmd[3:], user_qq)
        elif re.match("^ftxt.{1,}", cmd):  # save format TEXT reply
            return self.save_ftext_reply(cmd[4:], user_qq)
        elif re.match("^alias.{1,}", cmd):  # save alias
            return self.save_alias(cmd[5:])
        elif re.match("^ptxt.{1,}", cmd):  # save private text
            return self.save_private_text_reply(cmd[4:], user_qq)

    def handle_set_cmd(self, cmd, user_qq, target):
        if not self.check_admin(user_qq):
            return

        if re.match("^cmd", cmd):
            cmd, arg = self.get_next_arg(cmd)
            self.set_cmd_level(cmd[3:], arg)
        elif re.match("^user", cmd):
            cmd, arg = self.get_next_arg(cmd)
            self.set_permission(target, arg)
        elif re.match("^md5", cmd):
            if len(cmd) > 3:
                self.use_md5 = 0
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "md5 off"
            else:
                self.use_md5 = 1
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "md5 on"
        elif re.match("^type", cmd):
            cmd, arg = self.get_next_arg(cmd)
            self.set_cmd_type(cmd[4:], arg)

    def handle_check_cmd(self, cmd, user_qq):
        if re.match("^user", cmd):
            self.check_user(user_qq)

    def check_user(self, user_qq):
        self.user_info = get_user(user_qq)
        self.reply_type = REPLY_TYPE.TEXT
        self.reply = "你的权限为:【{}】".format(self.user_info.permission)
        self.reply_at = int(user_qq)

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
        elif cmd_type == CMD_TYPE.VOICE:
            self.random_voice(arg)

    def random_text(self, tag, user_id=0):
        reply_info = None
        if len(tag):
            replies = self.db.get_reply_by_tag(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, tag)
            count = len(replies)
            if count > 0:
                ind = random.randint(1, count) - 1
                reply_info = replies[ind]
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.TEXT_TAG])
            reply_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, reply_id, user_id)

        if reply_info:
            self.reply = reply_info.reply
            self.reply_type = REPLY_TYPE.TEXT
            self.usage_increase(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                                CMD_TYPE.TEXT_TAG, reply_info.reply_id)
        elif user_id:
            self.reply = "你好像没有设置私人回复捏"
            self.reply_type = REPLY_TYPE.TEXT

    def random_ftext(self, arg):
        if len(arg) == 0:
            return
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.TEXT_FORMAT])
            reply_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_FORMAT, reply_id)

        if reply_info:
            self.reply = reply_info.reply.format(arg)
            self.reply_type = REPLY_TYPE.TEXT
            self.usage_increase(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                                CMD_TYPE.TEXT_FORMAT, reply_info.reply_id)

    def _random_pic(self, tag) -> replyInfo:
        reply_info = None
        if len(tag):
            replies = self.db.get_reply_by_tag(self.cmd_info.cmd_id, CMD_TYPE.PIC, tag)
            count = len(replies)
            if count > 0:
                ind = random.randint(1, count) - 1
                reply_info = replies[ind]
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.PIC])
            reply_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.PIC, reply_id)
        if reply_info:
            self.usage_increase(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                                CMD_TYPE.PIC, reply_info.reply_id)

        return reply_info

    def random_pic(self, arg):
        if self.use_md5 and self.group_flag:
            self.random_pic_md5(arg)
        else:
            self.random_pic_path(arg)

    def random_pic_md5(self, tag):
        pic_info = self._random_pic(tag)
        if pic_info:
            self.reply = pic_info.md5
            self.reply_type = REPLY_TYPE.PIC_MD5
            self.reply2 = pic_info.reply

    def random_pic_path(self, tag):
        pic_info = self._random_pic(tag)
        if pic_info:
            file_name = '{}.{}'.format(pic_info.md5, pic_info.file_type)
            file_name = file_name.replace('/', 'SLASH')  # avoid path revolving issue
            file_name = os.path.join(self.cur_dir, file_name)
            self.reply = file_name
            self.reply_type = REPLY_TYPE.PIC_PATH
            self.reply2 = pic_info.reply

    def random_voice(self, tag):
        voice_info = None
        if len(tag):
            voice_info = self.db.get_reply_by_tag(self.cmd_info.cmd_id, CMD_TYPE.VOICE, tag)
        else:
            reply_id = random.randint(1, self.cmd_info.sequences[CMD_TYPE.VOICE])
            voice_info = self.db.get_reply(self.cmd_info.cmd_id, CMD_TYPE.VOICE, reply_id)

        if voice_info:
            self.usage_increase(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                                CMD_TYPE.VOICE, voice_info.reply_id)
            self.reply_type = REPLY_TYPE.VOICE
            self.reply = os.path.join(voice_dir,
                                      "{}/{}.{}".format(self.cmd_info.cmd, voice_info.tag, voice_info.file_type))

    @staticmethod
    def find_imgtype(type_str):
        prefix = 'image/'
        img_type = None
        index = type_str.find(prefix)
        if index == 0:
            img_type = type_str[len(prefix):]
        return img_type

    def parse_pic(self, ctx: Union[GroupMsg, FriendMsg]):
        if ctx.MsgType != MsgTypes.PicMsg:
            return None

        content = ""
        pic_obj = PicObj()
        if isinstance(ctx, FriendMsg):
            pics = friend.pic(ctx)
            pic_obj.user = str(ctx.FromUin)
            pic_obj.Url = pics.FriendPic[0].Url
            pic_obj.Md5 = pics.FriendPic[0].FileMd5
            content = pics.Content
        elif isinstance(ctx, GroupMsg):
            pics = group.pic(ctx)
            pic_obj.user = str(ctx.FromUserId)
            pic_obj.Url = pics.GroupPic[0].Url
            pic_obj.Md5 = pics.GroupPic[0].FileMd5
            content = pics.Content
        if re.match("^_savepic.{1,}", content):
            pic_obj.cmd, pic_obj.tag, pic_obj.reply = self.save_cmd_parse(content[8:])
            pic_obj.private = False
        elif re.match("^_saveppic.{1,}", content):
            pic_obj.cmd, pic_obj.tag, pic_obj.reply = self.save_cmd_parse(content[9:])
            pic_obj.private = True

        return pic_obj

    def save_pic(self, pic: PicObj, no_checkout=False):
        if pic.Url and (no_checkout or self.checkout(pic.cmd, pic.user, cmd_type=CMD_TYPE.PIC, create=True,
                                                     private=pic.private)):
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
                if pic.private:
                    max_id = self.db.get_private_reply_max_id(self.user_info.user_id, self.cmd_info.cmd_id)
                    count = self.db.get_private_reply_count(self.user_info.user_id, self.cmd_info.cmd_id)
                    if count >= self.user_info.private_limit:
                        self.reply_type = REPLY_TYPE.TEXT
                        self.reply = f"【系统错误: 私人回复超过上限了！】"
                        raise ReplyLimitExceedException
                    max_id += 1
                    self.db.add_private_reply(self.cmd_info.cmd_id, CMD_TYPE.PIC, max_id, self.user_info.user_id,
                                              pic.Md5, img_type, pic.reply)
                    self.reply_type = REPLY_TYPE.TEXT
                    self.reply = f"私人图片回复已存储，关键词【{self.cmd_info.cmd}】 回复【{pic.reply}】"
                else:
                    self.cmd_info.sequences[CMD_TYPE.PIC] += 1
                    new_reply_id = self.cmd_info.sequences[CMD_TYPE.PIC]
                    self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.PIC, new_reply_id, tag=pic.tag, md5=pic.Md5,
                                      file_type=img_type, reply=pic.reply, user_id=self.user_info.user_id)
                    self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.PIC, new_reply_id)
                    self.reply_type = REPLY_TYPE.TEXT
                    self.reply = f"图片回复已存储，关键词【{self.cmd_info.cmd}】 tag【{pic.tag}】 回复【{pic.reply}】"
                return True

            except Exception as e:
                logger.warning('Failed to get picture from url:{},{}'.format(pic.Url, e))
                raise

        return False

    @staticmethod
    def get_next_arg(cmd):
        space_index = cmd.find(' ')
        if space_index > 0:
            return cmd[0:space_index], cmd[space_index + 1:]
        else:
            return cmd, None

    @staticmethod
    def save_cmd_parse(cmd):
        cmd = cmd.strip()
        arg = ""
        reply = ""
        space_index = cmd.find(' ')
        if space_index > 0:
            arg = cmd[space_index + 1:]
            cmd = cmd[0:space_index]

        if arg == "":
            space_index = cmd.find('reply')
            if space_index >= 0:
                reply = reply[space_index + 5:]
                cmd = cmd[:space_index]
                cmd = cmd.strip()
        else:
            space_index = arg.find('reply')
            if space_index >= 0:
                reply = arg[space_index + 5:]
                arg = arg[0:space_index]
                arg = arg.strip()

        return cmd, arg, reply

    def save_text_reply(self, cmd, user_qq):
        logger.info('saving {}'.format(cmd))
        cmd, tag, reply = self.save_cmd_parse(cmd)
        if len(cmd) and reply and len(reply):
            if self.checkout(cmd, user_qq, cmd_type=CMD_TYPE.TEXT_TAG, create=True):
                new_reply_id = self.cmd_info.sequences[CMD_TYPE.TEXT_TAG] + 1
                self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, new_reply_id, tag=tag, reply=reply,
                                  user_id=self.user_info.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, new_reply_id)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "回复存储成功，{}({}):{}".format(cmd, tag, reply)
            else:
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "这个关键词好像用不了捏"

    def save_ftext_reply(self, cmd, user_qq):
        cmd, arg, reply = self.save_cmd_parse(cmd)
        if len(cmd) and len(reply):
            if self.checkout(cmd, user_qq, cmd_type=CMD_TYPE.TEXT_FORMAT, create=True):
                new_reply_id = self.cmd_info.sequences[CMD_TYPE.TEXT_FORMAT] + 1
                self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_FORMAT, new_reply_id, reply=reply,
                                  user_id=self.user_info.user_id)
                self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.TEXT_FORMAT, new_reply_id)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "定形回复存储成功，{}({}):{}".format(cmd, arg, reply)
            else:
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "这个关键词好像用不了捏"

    def save_alias(self, cmd):
        space_index = cmd.find(' ')
        if space_index > 0:
            p_cmd = cmd[space_index + 1:]
            p_cmd = p_cmd.strip()
            cmd = cmd[0:space_index]
            if self.checkout(cmd, super_user, check_active=False):
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "关键词【{}】已存在，不可以设置为同义词捏".format(cmd)
                return
            if self.checkout(p_cmd, super_user):
                self.add_alias(cmd, self.cmd_info.cmd_id, 0, 0)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "同义词设置成功:{} = {}".format(cmd, p_cmd)

    @staticmethod
    def split_file_type(file_name: str):
        ext_ind = file_name.rfind('.')
        if ext_ind == -1:
            return file_name, ""
        else:
            return file_name[:ext_ind], file_name[ext_ind + 1:]

    def scan_voice_sub_dir(self, cmd, sub_dir):
        record = ""
        for voice_file in os.listdir(sub_dir):
            print("find:" + voice_file)
            if os.path.isfile(os.path.join(sub_dir, voice_file)):
                file, ext = self.split_file_type(voice_file)
                if self.db.get_reply_by_tag(self.cmd_info.cmd_id, CMD_TYPE.VOICE, file):
                    continue
                else:
                    self.cmd_info.sequences[CMD_TYPE.VOICE] += 1
                    voice_seq = self.cmd_info.sequences[CMD_TYPE.VOICE]
                    self.db.add_reply(self.cmd_info.cmd_id, CMD_TYPE.VOICE, voice_seq,
                                      tag=file, file_type=ext, user_id=self.user_info.user_id)
                    self.db.set_cmd_seq(self.cmd_info.cmd_id, CMD_TYPE.VOICE, voice_seq)
                    record += "{}:{} 已添加\n".format(cmd, file)
        return record

    def scan_voice_dir(self):
        self.reply_type = REPLY_TYPE.TEXT
        reports = ""
        print("start voice scanning")
        voice_subs = os.listdir(voice_dir)
        for cmd in voice_subs:
            sub_dir = os.path.join(voice_dir, cmd)
            print("find:" + sub_dir)
            if os.path.isdir(sub_dir):
                if not self.checkout(cmd, super_user, cmd_type=CMD_TYPE.VOICE, create=True):
                    self.reply = "命令索引创建/查找失败"
                    return
                reports += self.scan_voice_sub_dir(cmd, sub_dir)

        self.reply = reports

    def save_private_text_reply(self, cmd, user_qq):
        logger.info('saving {}'.format(cmd))
        cmd, tag, reply = self.save_cmd_parse(cmd)
        if len(cmd) and reply and len(reply):
            if self.checkout(cmd, user_qq, cmd_type=CMD_TYPE.TEXT_TAG, create=True, private=True):
                max_id = self.db.get_private_reply_max_id(self.user_info.user_id, self.cmd_info.cmd_id)
                count = self.db.get_private_reply_count(self.user_info.user_id, self.cmd_info.cmd_id)
                if count >= self.user_info.private_limit:
                    self.reply_type = REPLY_TYPE.TEXT
                    self.reply = f"【系统错误: 私人回复超过上限了！】"
                    raise ReplyLimitExceedException
                self.db.add_private_reply(self.cmd_info.cmd_id, CMD_TYPE.TEXT_TAG, max_id + 1,
                                          user_id=self.user_info.user_id, reply=reply)
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "私人回复存储成功，{}({}):{}".format(cmd, tag, reply)
            else:
                self.reply_type = REPLY_TYPE.TEXT
                self.reply = "这个关键词好像用不了捏"

    def handle_private_cmd(self):
        reply_info = self.random_private_reply()
        if reply_info.type == CMD_TYPE.PIC:
            self.reply_type = REPLY_TYPE.PIC_MD5
            self.reply = reply_info.md5
            self.reply2 = reply_info.reply
        elif reply_info.type == CMD_TYPE.TEXT_TAG:
            self.reply_type = REPLY_TYPE.TEXT
            self.reply = reply_info.reply

    def random_private_reply(self) -> replyInfo:
        reply_info = None
        replies = self.db.get_private_reply(self.user_info.user_id, self.cmd_info.cmd_id)
        count = len(replies)
        if count > 0:
            ind = random.randint(1, count) - 1
            reply_info = replies[ind]
            self.usage_increase(self.user_info.user_id, self.cmd_info.orig_id, self.cmd_info.cmd_id,
                                replies[ind].type, replies[ind].reply_id, private=True)
        return reply_info

    def usage_increase(self, user_id, orig_id, cmd_id, cmd_type, reply_id, private=False):
        if user_record_level == 0:  # do not save record
            return
        elif user_record_level == 1:  # save cmd level record
            cmd_type = 0
            reply_id = 0
        self.db.used_inc(user_id, orig_id, cmd_id,
                         cmd_type, reply_id, private=private)


# 将 plugin 作为特殊cmd使用 type=1000
class plugin_manager:
    def __init__(self, name="", cmd_id=0):
        self.plugin_name = name.upper()
        self.cmd_id = cmd_id
        self.db = self.db = cmdDB()

    def set_plugin_name(self, name):
        self.plugin_name = name.upper()

    def set_plugin_id(self, cmd_id):
        self.cmd_id = cmd_id

    def checkout(self, group_qq=0, group_qq_s="", cmd_id=0, create=False) -> bool:
        if group_qq:
            group_qq_s = str(group_qq)
        group_info = get_group(group_qq_s)
        if not group_info:
            return False
        if cmd_id:  # if cmd_id is given, no need to retrieve id from db
            self.cmd_id = cmd_id
        else:
            cmd_info = self.db.get_cmd(self.plugin_name)
            if not cmd_info:
                if create:
                    cmd_info = self.db.add_alias(self.plugin_name, 0, CMD_TYPE.PLUGIN, 0)
            self.cmd_id = cmd_info.cmd_id

        ret = self.db.is_group_cmd_enabled(group_info.group_id, self.cmd_id)
        if ret:
            return True
        elif not ret and ret != 0:  # returns None then create one
            self.db.set_group_cmd_status(group_info.group_id, self.cmd_id, 1)
            return True
        else:
            return False

    def bind(self, ctx: GroupMsg) -> bool:
        if not isinstance(ctx, GroupMsg):
            return False
        return self.checkout(ctx.FromGroupId, create=True)

    def app_usage(self, user_qq):  # increase plugin usage record
        if user_record_level == 0:  # do not save record
            return
        user_info = get_user(user_qq)
        if user_info:
            self.db.used_inc(user_info.user_id, self.cmd_id, self.cmd_id, CMD_TYPE.PLUGIN, 0)
