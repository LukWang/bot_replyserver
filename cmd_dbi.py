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

#enums
PIC = 1
TEXT_TAG = 2
TEXT_FORMAT = 3
VOICE = 4

cmdTypes[PIC, TEXT_TAG, TEXT_FORMAT, VOICE]

class cmdInfo:
    id: int
    cmd: str
    type: int
    active: int
    sequence: int

class picInfo:
    cmd_id: int
    id: int
    active: int
    tag: str
    md5: str
    file_type: str
    reply:str
    time_used: int

class replyInfo:
    cmd_id: int
    id: int
    active: int
    has_arg: int
    tag: str
    type: int
    reply: str
    time_used: int




class aliasInfo:
    

class cmdDB:
    def __init__(self):
        self.conn = sqlite3.connect(db_schema, check_same_thread=False)
        self.db = self.conn.cursor()

    def get_cmd_info(self, name):
        cmd_info = None
        self.db.execute('select id, type, active, amount from cmd_collection where cmd = ?', (name,))
        row = self.db.fetchone()
        if row:
            cmd_info = cateInfo()
            cmd_info.id = row[0]
            cmd_info.cmd = name
            cmd_info.type = row[1]
            cmd_info.active = row[2]
            cmd_info.sequence = row[3]

        return cate_info

    def add_cmd(self, cmd, type):
        if type not in cmdTypes:
            raise Exception("Invalid cmd type")
        self.db.execute('insert into cmd_collection(cmd, type, active, amount) values(?, ?, 0)', (name, type))
        self.conn.commit()

    def inc_cmd_seq(self, id, amount):
        self.db.execute('update cmd_collection set amount = amount + ? where id = ?', (amount, id))
        self.conn.commit()

    def set_cmd_seq(self, id, amount):
        self.db.execute('update cmd_collection set amount = ? where id = ?',(amount, id))
        self.conn.commit()

    def set_cmd_active(self, id, active)
        self.db.execute('update cmd_collection set active = ? where id = ?',(active, id))
        self.conn.commit()

    #reply operation
    def add_pic(self, cmd_id, id, tag, md5, file_type, reply):
        self.db.execute('insert into replies(cmd_id, id, active, has_arg, tag, type, hash, file_type, reply, stamp, time_used) 
                                      values(?,      ?,  1,      0,       1,   ?,    ?,    ?,         ?,     DATE("now"),0)', 
                                      (      cmd_id, id,                       PIC,  md5,  file_type, reply))
        self.conn.commit()

    def get_pic(self, cmd, id):
        pic_info = None
        self.db.execute('select hash, file_type, active, tag, reply, time_used from replies where cmd_id = ? and id = ?', (cmd, id))
        row = self.db.fetchone()
        if row:
            pic_info = picInfo()
            pic_info.cmd = cate
            pic_info.id = id
            pic_info.md5 = row[0]
            pic_info.type = row[1]
            pic_info.time_used = row[2]
        return pic_info
    
    def pic_use_inc(self, cate, id):
        self.db.execute('update pics set time_used = time_used + 1 where category = ? and sequence = ?', (cate, id))
        self.conn.commit()
