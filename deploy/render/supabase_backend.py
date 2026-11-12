"""Supabase backend for the Render entrypoint; never falls back to local files."""
import os
import re
import urllib.request
import urllib.error
from urllib.parse import quote,urlsplit
from zhiwei import server

class Storage:
    def __init__(self):
        self.url=os.environ['SUPABASE_URL'].rstrip('/')
        self.key=os.environ['SUPABASE_SERVICE_ROLE_KEY']
        self.bucket=os.environ.get('SUPABASE_BUCKET','zhiwei-media')
        parsed=urlsplit(self.url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/'):raise RuntimeError('SUPABASE_URL must be an HTTPS project origin')
    def request(self,path,data=None,mime='application/octet-stream'):
        request=urllib.request.Request(self.url+'/storage/v1/object/'+quote(self.bucket,safe='')+'/'+quote(path,safe='/'),data=data,method='POST' if data is not None else 'GET',headers={'Authorization':'Bearer '+self.key,'apikey':self.key,'Content-Type':mime})
        try:
            with urllib.request.urlopen(request,timeout=45) as response:return response.read()
        except urllib.error.HTTPError as error:
            # Never include response bodies, headers or credentials in user errors.
            raise server.Problem(503,'素材存储暂不可用，请稍后重试') from None
    def put(self,path,data,mime):self.request(path,data,mime)
    def get(self,path):return self.request(path)

class Row:
    def __init__(self,values,storage):self.values=values;self.storage=storage;self.cached=None
    def keys(self):return self.values.keys()
    def __getitem__(self,key):
        if isinstance(key,int):key=list(self.values)[key]
        value=self.values[key]
        if key=='bytes':
            if self.cached is None:self.cached=self.storage.get(value)
            return self.cached
        return value

class Cursor:
    def __init__(self,cursor,storage):self.cursor=cursor;self.storage=storage
    @property
    def rowcount(self):return self.cursor.rowcount
    def fetchone(self):
        row=self.cursor.fetchone();return Row(row,self.storage) if row is not None else None
    def fetchall(self):return [Row(row,self.storage) for row in self.cursor.fetchall()]
    def __iter__(self):return iter(self.fetchall())

# Only translate the fixed SQL statements authored in server.py. Values always
# remain bound parameters; SQLite SQL from callers is never accepted over HTTP.
def postgres_sql(sql):
    compact=' '.join(sql.strip().split())
    if compact in ('BEGIN','BEGIN IMMEDIATE'):return 'SELECT pg_advisory_xact_lock(741806129)',False
    if compact.startswith('CREATE TABLE IF NOT EXISTS deleted_assets') or compact.startswith('CREATE TABLE IF NOT EXISTS feedback'):
        return 'SELECT 1',False  # Owned by the explicit migration, not request handling.
    ignore=compact.startswith('INSERT OR IGNORE INTO ')
    replace=compact.startswith('INSERT OR REPLACE INTO ')
    translated=sql.replace('INSERT OR IGNORE INTO ','INSERT INTO ').replace('INSERT OR REPLACE INTO ','INSERT INTO ').replace('?','%s')
    if ignore:translated+=' ON CONFLICT DO NOTHING'
    if replace:
        if 'INTO assets ' in translated:translated+=' ON CONFLICT(id) DO UPDATE SET course=EXCLUDED.course,name=EXCLUDED.name,mime=EXCLUDED.mime,checksum=EXCLUDED.checksum,bytes=EXCLUDED.bytes'
        elif 'INTO deleted_assets ' in translated:translated+=' ON CONFLICT(id) DO UPDATE SET course=EXCLUDED.course,deleted_at=EXCLUDED.deleted_at'
        else:raise RuntimeError('Unsupported upsert')
    return translated,compact.startswith(('INSERT INTO assets VALUES','INSERT OR REPLACE INTO assets VALUES'))

class Connection:
    def __init__(self,conn,storage):self.conn=conn;self.storage=storage
    def __enter__(self):return self
    def __exit__(self,kind,value,tb):
        if kind:self.conn.rollback()
        else:self.conn.commit()
    def close(self):self.conn.close()
    def execute(self,sql,parameters=()):
        translated,media=postgres_sql(sql);parameters=list(parameters)
        if media:
            aid,cid,name,mime,checksum,raw=parameters
            if len(raw)>10*1024*1024:raise server.Problem(413,'免费体验版单文件上限 10 MB')
            key=cid+'/'+aid+'/'+checksum
            found=self.conn.execute('SELECT size FROM asset_objects WHERE key=%s',(key,)).fetchone()
            if not found:
                total=self.conn.execute('SELECT COALESCE(SUM(size),0) AS size FROM asset_objects').fetchone()['size']
                if total+len(raw)>700*1024*1024:raise server.Problem(413,'测试站素材额度已接近免费上限，请先联系维护者')
                self.storage.put(key,raw,mime)
                self.conn.execute('INSERT INTO asset_objects(key,size) VALUES(%s,%s) ON CONFLICT DO NOTHING',(key,len(raw)))
            parameters[-1]=key
        try:return Cursor(self.conn.execute(translated,parameters),self.storage)
        except Exception as error:
            # Match the existing API's conflict handling without exposing SQL.
            if getattr(error,'sqlstate',None)=='23505':raise server.sqlite3.IntegrityError('duplicate value') from None
            if getattr(error,'sqlstate',None) in ('40001','40P01'):raise server.Problem(412,'保存冲突，请刷新后选择继续编辑内容') from None
            raise

def connect():
    import psycopg
    from psycopg.rows import dict_row
    # Session pooler supports long-running Python services and IPv4 hosts.
    conn=psycopg.connect(os.environ['DATABASE_URL'],sslmode='require',connect_timeout=15,prepare_threshold=None,row_factory=dict_row)
    try:
        conn.execute('SET search_path TO zhiwei,pg_catalog')
        # Small closed-beta workload: serialize requests so the original
        # SQLite restore/delete transaction semantics remain intact.
        conn.execute('SELECT pg_advisory_xact_lock(741806129)')
        return Connection(conn,Storage())
    except Exception:conn.close();raise
