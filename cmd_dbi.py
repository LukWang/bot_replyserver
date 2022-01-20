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
    orig_id: int
    cmd: str
    active: int
    cmd_type: int  # a bit map indicating supported reply type
    level: int  # permission level, default 1
    sequences: dict


class replyInfo:
    cmd_id: int
    type: int
    reply_id: int
    tag: str
    md5: str
    file_type: str
    reply: str


class aliasInfo:
    cmd_id: int
    cmd: str
    p_cmd_id: int
    active: int


class userInfo:
    user_id: int
    permission: int
    qq: str
    

class cmdDB:
    def __init__(self):
        self.conn = sqlite3.connect(db_schema, check_same_thread=False)
        self.db = self.conn.cursor()

    # alias operations
    def add_alias(self, new_cmd, parent, reply_type, level):
        self.db.execute("insert into cmd_alias(cmd, p_cmd_id, active, type, level, sequence_1, sequence_2, sequence_4, sequence_8) "
                                       "values(?,   ?,        1,      1,    ?,     0, 0, 0, 0)", (new_cmd, parent, reply_type, level))
        self.conn.commit()
        return self.get_real_cmd(new_cmd)

    def make_parent(self, cmd):
        self.db.execute("update cmd_alias set p_cmd_id = 0 where cmd = ?", (cmd, ))

    def set_cmd_active(self, cmd_id, active):
        self.db.execute('update cmd_alias set active = ? where id = ?', (active, cmd_id))
        self.conn.commit()

    def set_cmd_seq(self, cmd_id, type_id, sequence_id):
        self.db.execute('update cmd_alias set sequence_{} = ? where id = ?'.format(type_id), (sequence, cmd_id))
        self.conn.commit()

    def set_cmd_type(self, cmd_id, reply_type):
        self.db.execute('update cmd_alias set type = ? where id = ?', (reply_type, cmd_id))
        self.conn.commit()

    def set_cmd_level(self, cmd_id, level):
        self.db.execute('update cmd_alias set level = ? where id = ?', (level, cmd_id))
        self.conn.commit()

    def get_real_cmd(self, cmd):
        orig_cmd_id = 0
        cmd_info = None
        self.db.execute("select id, p_cmd_id, active, type, level, sequence_1, sequence_2, sequence_4, sequence_8 from cmd_alias where cmd = ?", (cmd,))
        row = self.db.fetchone()
        if row:
            orig_cmd_id = row[0]
        while row and row[1] > 0 and row[2] != 0:
            self.db.execute("select id, p_cmd_id, active, type, level, sequence_1, sequence_2, sequence_4, sequence_8 from cmd_alias where id = ?", (row[1],))
            row = self.db.fetchone()
        if row and row[2] > 0:
            cmd_info = cmdInfo()
            cmd_info.cmd_id = row[0]
            cmd_info.orig_id = orig_cmd_id
            cmd_info.cmd = cmd
            cmd_info.active = row[2]
            cmd_info.cmd_type = row[3]
            cmd_info.level = row[4]
            cmd_info.sequences[CMD_TYPE.PIC] = row[5]
            cmd_info.sequences[CMD_TYPE.TEXT_TAG] = row[6]
            cmd_info.sequences[CMD_TYPE.TEXT_FORMAT] = row[7]
            cmd_info.sequences[CMD_TYPE.VOICE] = row[8]
        return cmd_info

    # reply operation
    def add_reply(self, cmd_id, reply_type, reply_id, tag="", md5="", file_type="", reply="", user_id=0):
        self.db.execute('insert into replies(cmd_id,  type,       id,       tag, hash, file_type, reply, stamp,       user_id, time_used) '
                                      'values(?,      ?,          ?,        ?,   ?,    ?,         ?,     DATE("now"), ?,       0)',
                                             (cmd_id, reply_type, reply_id, tag, md5,  file_type, reply,              user_id))
        self.conn.commit()

    def get_reply(self, cmd_id, reply_type=0, reply_id=0, get_all=False):
        reply_info = None
        sql_str = "select type, id, tag, hash, file_type, reply from replies where cmd_id = ?"
        if reply_type > 0:
            sql_str += " and type = ?"
        else:
            sql_str += " and type > 0"
        if reply_id:
            sql_str += " and id = ?"

        if get_all:
            sql_str += " order by id"

        self.db.execute(sql_str, (cmd_id, reply_type))
        if get_all:
            return self.db.fetchall()
        else:
            row = self.db.fetchone()
            if row:
                reply_info = replyInfo()
                reply_info.cmd_id = cmd_id
                reply_info.type = row[0]
                reply_info.reply_id = row[1]
                reply_info.tag = row[2]
                reply_info.md5 = row[3]
                reply_info.file_type = row[4]
                reply_info.reply = row[5]
        return reply_info

    def get_reply_by_tag(self, cmd_id, reply_type, tag):
        reply_info = None
        self.db.execute("select id, tag, hash, file_type, reply from replies where cmd_id = ? and type = ? and tag like '%" + tag + "%' order by time_used", (cmd_id,reply_type))
        row = self.db.fetchone()
        if row:
            reply_info = replyInfo()
            reply_info.cmd_id = cmd_id
            reply_info.type = reply_type
            reply_info.reply_id = row[0]
            reply_info.tag = row[1]
            reply_info.md5 = row[2]
            reply_info.file_type = row[3]
            reply_info.reply = row[4]
        return reply_info

    # user operations
    def add_user(self, user_qq):
        self.db.execute('insert into users(qq_id, first_used, permission) values(?, DATE("now"), ?)', (user_qq, 1))
        self.conn.commit()

    def get_user(self, user_qq):
        user_info = None
        self.db.execute('select user_id, permission from users where qq_id = ?', (user_qq,))
        row = self.db.fetchone()
        if row:
            user_info = userInfo()
            user_info.user_id = row[0]
            userInfo.permission = row[1]
            userInfo.qq = user_qq

        return user_info

    def used_inc(self, user_id, orig_id, cmd_id, reply_type, reply_id):
        self.db.execute('update replies set time_used = time_used + 1 where cmd_id = ? and type = ? and id = ?', (cmd_id, reply_type, reply_id))
        try:
            self.db.execute("update user_records set time_used = time_used + 1, last_used = DATE('now') "
                            "where user_id = ? and orig_id = ? and cmd_id = ? and type = ? and reply_id = ?",
                            (user_id, orig_id, cmd_id, reply_type, reply_id))
        except sqlite3.DatabaseError:
            self.db.execute("insert into user_records(user_id, orig_cmd_id, cmd_id, type, reply_id, time_used， first_used, last_used date) "
                                              "values(?,       ?,           ?,      ?,    ?,        1,          DATE('now'),DATE('now'))",
                                                     (user_id, orig_id, cmd_id, reply_type, reply_id))

        self.conn.commit()





