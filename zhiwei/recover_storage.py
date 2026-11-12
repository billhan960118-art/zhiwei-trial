"""Merge a known legacy database into the durable store without replacing data."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import time
import server

def merge(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination: raise ValueError('源库与目标库相同')
    if not source.is_file() or not destination.is_file(): raise ValueError('数据库必须已存在')
    stamp = str(time.time_ns())
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as old, closing(sqlite3.connect(destination)) as new:
        old.row_factory = new.row_factory = sqlite3.Row
        for db, file in ((old,source),(new,destination)):
            with closing(sqlite3.connect(file.with_name(file.name+'.backup-'+stamp))) as backup:
                db.backup(backup)
                if backup.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('备份校验失败')
        mapping = {}
        with new:
            new.execute('BEGIN IMMEDIATE')
            for u in old.execute('SELECT * FROM users'):
                existing = new.execute('SELECT id FROM users WHERE lower(email)=lower(?)',(u['email'],)).fetchone()
                mapping[u['id']] = existing['id'] if existing else u['id']
                if not existing: new.execute('INSERT INTO users VALUES(?,?,?,?)',tuple(u))
            tables = {r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in ('courses','revisions','releases','assets','sessions','imports','deleted_assets'):
                if table not in tables: continue
                if table=='deleted_assets': new.execute('CREATE TABLE IF NOT EXISTS deleted_assets(id TEXT PRIMARY KEY,course TEXT,deleted_at REAL)')
                columns = [r[1] for r in old.execute('PRAGMA table_info('+table+')')]
                key = 'token' if table=='sessions' else 'id'
                for row in old.execute('SELECT * FROM '+table):
                    values = dict(row)
                    for field in ('owner','user_id'):
                        if field in values: values[field] = mapping.get(values[field],values[field])
                    existing = new.execute('SELECT * FROM '+table+' WHERE '+key+'=?',(values[key],)).fetchone()
                    if existing:
                        if any(existing[k] != values[k] for k in columns): raise ValueError('存在不同内容的相同标识，已取消合并：'+table)
                    else: new.execute('INSERT INTO '+table+' ('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[values[k] for k in columns])
        if new.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('合并后完整性检查失败')
    return True

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--destination',required=True);args=parser.parse_args()
    merge(args.source,args.destination);print('合并成功；原库保留，两份合并前备份已建立。')
