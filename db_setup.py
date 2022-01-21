import sqlite3
import os, json
import re

db_schema = ''
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        db_schema = config['db_schema']
except:
    print('Cannot resolve db_schema name from config.json')
    raise

conn = sqlite3.connect(db_schema)
cur = conn.cursor()

try:
    with open('db_setup', 'r', encoding='utf-8') as f:
        for line in f.readlines():
            line = line.strip()
            if re.match("^#.*", line):
                continue
            print('Executing: ', line)
            cur.execute(line)
except:
    print('Failed to execute DB setup')
    raise
conn.commit()
conn.close()

print('DB setup finished')
