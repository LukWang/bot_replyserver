import sqlite3
import os, json
from enum import Enum
cur_file_dir = os.path.dirname(os.path.realpath(__file__))
db_schema = ''
try:
    with open(cur_file_dir + '/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        db_schema = config['db_schema']
        db_schema = os.path.join(cur_file_dir, db_schema)
except:
    print('Fail to get db_schema info')


# enums
class CMD_TYPE:
    PIC = 1
    TEXT_TAG = 2
    TEXT_FORMAT = 4
    VOICE = 8


class cmdInfo:
    cmd_id: int
    cmd: str
    type: int
    active: int
    sequence: int


class picInfo:
    cmd_id: int
    reply_id: int
    active: int
    tag: str
    type: str
    md5: str
    file_type: str
    reply:str
    time_used: int


class replyInfo:
    cmd_id: int
    reply_id: int
    active: int
    has_arg: int
    tag: str
    type: int
    reply: str
    time_used: int


class aliasInfo:
    cmd_id: int
    cmd: str
    p_cmd_id: int
    active: int
    

class cmdDB:
    def __init__(self):
        self.conn = sqlite3.connect(db_schema, check_same_thread=False)
        self.db = self.conn.cursor()

    def get_cmd_info(self, cmd_id = None, cmd = None):
        cmd_info = None
        if cmd_id:
            self.db.execute('select id, type, active, amount, cmd from cmd_collection where id = ?', (cmd_id,))
        elif cmd:
            self.db.execute('select id, type, active, amount from cmd_collection where cmd = ?', (cmd,))
        else:
            return None

        row = self.db.fetchone()
        if row:
            cmd_info = cmdInfo()
            cmd_info.cmd_id = row[0]
            if cmd:
                cmd_info.cmd = cmd
            else:
                cmd_info.cmd = row[4]
            cmd_info.type = row[1]
            cmd_info.active = row[2]
            cmd_info.sequence = row[3]

        return cmd_info

    def add_cmd(self, cmd, type):
        self.db.execute('insert into cmd_collection(cmd, type, active, amount) values(?, ?, 1, 0)', (cmd, type))
        self.conn.commit()

    def disable_cmd(self, cmd_id, active):
        self.db.execute('update cmd_collection set active = ?  where id = ?', (active, cmd_id))
        self.conn.commit()

    def set_cmd_type(self, cmd_id, type):
        self.db.execute('update cmd_collection set type = ? where id = ?', (type, cmd_id))
        self.conn.commit()

    def inc_cmd_seq(self, cmd_id, amount):
        self.db.execute('update cmd_collection set amount = amount + ? where id = ?', (amount, cmd_id))
        self.conn.commit()

    def set_cmd_seq(self, cmd_id, amount):
        self.db.execute('update cmd_collection set amount = ? where id = ?',(amount, cmd_id))
        self.conn.commit()

    def set_cmd_active(self, cmd_id, active):
        self.db.execute('update cmd_collection set active = ? where id = ?',(active, cmd_id))
        self.conn.commit()

    # reply operation
    def add_pic(self, cmd_id, reply_id, md5, file_type, type, tag="", reply="", user_id = ""):
        self.db.execute('insert into replies(cmd_id, id, active, has_arg, tag, type, hash, file_type, reply, stamp, time_used, user_id) '
                                      'values(?,      ?,  1,      0,      ?,   ?,    ?,    ?,         ?,     DATE("now"),0,    ?)',
                                             (cmd_id, reply_id,           tag, type, md5,  file_type, reply,                   user_id))
        self.conn.commit()

    def add_reply(self, cmd_id, reply_id, has_arg, tag, type, reply, user_id):
        self.db.execute('insert into replies(cmd_id, id, active, has_arg, tag, type, hash, file_type, reply, stamp, time_used, user_id) '
                                      'values(?,      ?,  1,     ?,       ?,   ?,    " ",  " ",       ?,     DATE("now"),0,    ?)',
                                             (cmd_id, reply_id,  has_arg, tag, type,                  reply,                   user_id))
        self.conn.commit()

    def get_pic(self, cmd_id, reply_id):
        pic_info = None
        self.db.execute('select hash, file_type, active, tag, reply, time_used from replies where cmd_id = ? and id = ?', (cmd_id, reply_id))
        row = self.db.fetchone()
        if row:
            pic_info = picInfo()
            pic_info.cmd_id = cmd_id
            pic_info.reply_id = reply_id
            pic_info.type = CMD_TYPE.PIC
            pic_info.md5 = row[0]
            pic_info.file_type = row[1]
            pic_info.active = row[2]
            pic_info.tag = row[3]
            pic_info.reply = row[4]
            pic_info.time_used = row[5]
        return pic_info

    def get_pic_by_tag(self, cmd_id, tag):
        pic_info = None
        self.db.execute("select id, hash, file_type, active, tag, reply, time_used from replies where cmd_id = ? and tag like '" + tag + "%' order by time_used", (cmd_id,))
        row = self.db.fetchone()
        if row:
            pic_info = picInfo()
            pic_info.cmd_id = cmd_id
            pic_info.reply_id = row[0]
            pic_info.type = CMD_TYPE.PIC
            pic_info.md5 = row[1]
            pic_info.file_type = row[2]
            pic_info.active = row[3]
            pic_info.tag = row[4]
            pic_info.reply = row[5]
            pic_info.time_used = row[6]
        return pic_info

    def get_reply(self, cmd_id, reply_id):
        reply_info = None
        self.db.execute("select has_arg, active, type, tag, reply, time_used from replies where cmd_id = ? and id = ?", (cmd_id, reply_id))
        row = self.db.fetchone()
        if row:
            reply_info = replyInfo()
            reply_info.cmd_id = cmd_id
            reply_info.reply_id = reply_id
            reply_info.has_arg = row[0]
            reply_info.active = row[1]
            reply_info.type = row[2]
            reply_info.tag = row[3]
            reply_info.reply = row[4]
            reply_info.time_used = row[5]
        return reply_info

    def get_reply_by_tag(self, cmd_id, tag):
        reply_info = None
        self.db.execute("select id, has_arg, active, type, tag, reply, time_used from replies where cmd_id = ? and tag like '" + tag + "%' order by time_used", (cmd_id,))
        row = self.db.fetchone()
        if row:
            reply_info = replyInfo()
            reply_info.cmd_id = cmd_id
            reply_info.reply_id = row[0]
            reply_info.has_arg = row[1]
            reply_info.active = row[2]
            reply_info.type = row[3]
            reply_info.tag = row[4]
            reply_info.reply = row[5]
            reply_info.time_used = row[6]
        return reply_info
    
    def used_inc(self, cmd_id, reply_id):
        self.db.execute('update replies set time_used = time_used + 1 where cmd_id = ? and id = ?', (cmd_id, reply_id))
        self.conn.commit()

    # alias operations
    def add_alias(self, new_cmd, parent):
        self.db.execute("insert into cmd_alias(cmd, p_cmd_id, active) values(?, ?, 1) on conflict replace", (new_cmd, parent))
        self.conn.commit()

    def make_parent(self, cmd):
        self.db.execute("update cmd_alias set p_cmd_id = 0 where cmd = ?", (cmd, ))

    def disable(self, cmd):
        self.db.execute("update cmd_alias set active = 0 where cmd = ?", (cmd, ))

    def get_real_cmd(self, cmd):
        real_cmd_id = 0
        self.db.execute("select id, p_cmd_id, active from cmd_alias where ", (cmd,))
        row = self.db.fetchone()
        while row and row[1] > 0 and row[2] != 0:
            self.db.execute("select id, p_cmd_id, active from cmd_alias where ", (cmd,))
            row = self.db.fetchone()
        if row and row[2] > 0:
            real_cmd_id = row[0]
        return real_cmd_id



