"""Consistent SQLite backup including immutable media; restore only to a new directory."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import server

def backup(destination):
    destination = Path(destination)
    if destination.exists(): raise ValueError('拒绝覆盖已有备份')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with closing(server.connect()) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('备份完整性检查失败')

def restore(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists(): raise ValueError('恢复目标必须为新目录，禁止覆盖已有数据')
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('备份损坏')
        destination.mkdir(parents=True)
        with closing(sqlite3.connect(destination/'courses.sqlite')) as target: db.backup(target)

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore']);p.add_argument('path');p.add_argument('--destination');args=p.parse_args()
    if args.action=='backup': backup(args.path)
    else:
        if not args.destination: p.error('restore 需要 --destination 新目录')
        restore(args.path,args.destination)
    print('完整性检查通过')
