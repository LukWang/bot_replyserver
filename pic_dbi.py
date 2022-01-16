import sqlite3
import os, json
cur_file_dir = os.path.dirname(os.path.realpath(__file__))
db_schema = ''
try:
    with open(cur_file_dir + '/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        db_schema = config['db_schema']
        db_schema = os.path.join(cur_file_dir, db_schema)
except:
    print('Fail to get db_schema info')

class cateInfo:
    id: int
    name: str
    sequence: int

class picInfo:
    cate: int
    id: int
    md5: str
    type: str
    time_used: int 

class picDB:
    def __init__(self):
        self.conn = sqlite3.connect(db_schema, check_same_thread=False)
        self.db = self.conn.cursor()

    def get_cate_info(self, name):
        cate_info = None
        self.db.execute('select id, amount from pic_collection where pic_category = ?', (name,))
        row = self.db.fetchone()
        if row:
            cate_info = cateInfo()
            cate_info.id = row[0]
            cate_info.name = name
            cate_info.sequence = row[1]

        return cate_info

    def add_category(self, name):
        self.db.execute('insert into pic_collection(pic_category, amount) values(?, 0)', (name,))
        self.conn.commit()

    def increase(self, id, amount):
        self.db.execute('update pic_collection set amount = amount + ? where id = ?', (amount, id))
        self.conn.commit()

    def set_cate(self, id, amount):
        self.db.execute('update pic_collection set amount = ? where id = ?',(amount, id))
        self.conn.commit()

    #pic operation
    def add_pic(self, category, id, md5, type):
        self.db.execute('insert into pics values(?,?,?,?,DATE("now"),0)', (category, id, md5, type))
        self.conn.commit()

    def get_pic(self, cate, id):
        pic_info = None
        self.db.execute('select hash, type, time_used from pics where category = ? and sequence = ?', (cate, id))
        row = self.db.fetchone()
        if row:
            pic_info = picInfo()
            pic_info.cate = cate
            pic_info.id = id
            pic_info.md5 = row[0]
            pic_info.type = row[1]
            pic_info.time_used = row[2]
        return pic_info
    
    def pic_use_inc(self, cate, id):
        self.db.execute('update pics set time_used = time_used + 1 where category = ? and sequence = ?', (cate, id))
        self.conn.commit()
