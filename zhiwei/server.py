"""Zhiwei local application. Persistent data lives outside static/application files."""
from contextlib import closing
import base64
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
import webbrowser
import sys
import socket
import zipfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).parent
DATA = Path(os.environ.get('ZHIWEI_DATA', str(Path.home() / 'zhiwei-data')))
def uid(): return str(uuid.uuid4())
def encode(x): return json.dumps(x, ensure_ascii=False, separators=(',', ':'))
def digest(b): return hashlib.sha256(b).hexdigest()
def asset_name(name, mime):
    name = unquote(name).strip()
    # Older clients stored URL-encoded Chinese names, or displayed opaque IDs.
    stem = Path(name).stem.replace('-', '')
    if not name or (len(stem) >= 16 and all(c in '0123456789abcdefABCDEF' for c in stem)):
        return '图片素材' if mime.startswith('image/') else '视频素材'
    return name[:200]
class Problem(Exception):
    def __init__(self, status, message): self.status, self.message = status, message

def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / 'courses.sqlite', timeout=20)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,salt TEXT,password TEXT);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT,expires REAL);
    CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY,owner TEXT,title TEXT,revision INTEGER,draft TEXT,published TEXT);
    CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY,course TEXT,revision INTEGER,payload TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY,course TEXT,payload TEXT,hash TEXT,created REAL);
    CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,course TEXT,name TEXT,mime TEXT,checksum TEXT,bytes BLOB);
    CREATE TABLE IF NOT EXISTS deleted_assets(id TEXT PRIMARY KEY,course TEXT,deleted_at REAL);
    CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY,owner TEXT,payload TEXT);
    PRAGMA user_version=1;
    ''')
    return db

def validate(d):
    errors = []
    nodes = {n['id']: n for n in d['nodes'] if not n.get('archived')}
    anchors = {n['id']: {b['blockId'] for s in n['sections'] for b in s['blocks']} for n in nodes.values()}
    for n in nodes.values():
        if not n['title'].strip(): errors.append({'nodeId': n['id'], 'message': '知识点标题为空'})
        for s in n['sections']:
            for b in s['blocks']:
                data = b['data']
                if b['type'] == 'quiz' and (not data.get('options') or data.get('answer') not in [o['id'] for o in data['options']]):
                    errors.append({'nodeId': n['id'], 'blockId': b['blockId'], 'message': '自测答案无效'})
                if b['type'] == 'reference' and (data.get('target') not in nodes or (data.get('anchor') and data['anchor'] not in anchors.get(data['target'], set()))):
                    errors.append({'nodeId': n['id'], 'blockId': b['blockId'], 'message': '引用目标或锚点失效'})
    graph = {i: [] for i in nodes}
    seen = set()
    for r in d['relations']:
        a, b, kind = r['source'], r['target'], r['type']
        if a == b or a not in nodes or b not in nodes:
            errors.append({'message': '关系包含自身或归档/缺失节点'}); continue
        if kind not in ('prerequisite', 'derivation', 'application', 'reference', 'comparison'):
            errors.append({'message': '未知关系类型'}); continue
        key = (kind, *sorted([a, b])) if kind in ('reference', 'comparison') else (kind, a, b)
        if key in seen: errors.append({'message': '重复关系'})
        seen.add(key)
        if kind == 'prerequisite': graph[a].append(b)
    visiting, visited = set(), set()
    def walk(i):
        if i in visiting: return False
        if i in visited: return True
        visiting.add(i)
        if not all(walk(j) for j in graph[i]): return False
        visiting.remove(i); visited.add(i); return True
    if not all(walk(i) for i in graph): errors.append({'message': '前置关系存在循环'})
    items = {x['id']: x for x in d['outline']}
    for i in items:
        chain = set(); current = i
        while current:
            if current in chain or current not in items:
                errors.append({'message': '目录循环或父目录缺失'}); break
            chain.add(current); current = items[current].get('parent')
    return errors

def check_shape(d):
    if d.get('schemaVersion') != 1: raise Problem(422, '内容版本不受支持，保留原稿只读')
    ids = set()
    def unique(i):
        if not isinstance(i, str) or not i or i in ids: raise Problem(422, '标识重复或无效')
        ids.add(i)
    for key in ('nodes', 'outline', 'relations', 'templates'):
        if not isinstance(d.get(key), list): raise Problem(422, '内容结构无效')
        for x in d[key]: unique(x['id'])
    for n in d['nodes']:
        for s in n['sections']:
            unique(s['sectionId'])
            for b in s['blocks']:
                unique(b['blockId'])
                if b['type'] not in ('text', 'heading', 'formula', 'image', 'video', 'attachment', 'step', 'reference', 'quiz') or b.get('blockVersion') != 1:
                    raise Problem(422, '未知内容块，禁止有损保存；请导出原始内容')
    items = {x['id']: x for x in d['outline']}
    for item in items.values():
        chain = set()
        current = item['id']
        while current:
            if current in chain or current not in items: raise Problem(422, '目录存在循环或无效父章节')
            chain.add(current)
            current = items[current].get('parent')
    if any(n.get('chapter') and n['chapter'] not in items for n in d['nodes']):
        raise Problem(422, '知识点所属章节不存在，请先移动知识点')

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, status, data, mime='application/json; charset=utf-8', headers=None):
        raw = encode(data).encode() if not isinstance(data, bytes) else data
        self.send_response(status)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header('Content-Type', mime)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Zhiwei-Version', 'backup-1')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers(); self.wfile.write(raw)
    def do_GET(self): self.dispatch()
    def do_POST(self): self.dispatch()
    def do_PUT(self): self.dispatch()
    def do_DELETE(self): self.dispatch()
    def dispatch(self):
        try:
            with closing(connect()) as db:
                with db: self.route(db)
        except Problem as e: self.reply(e.status, {'errorCode': str(e.status), 'message': e.message, 'traceId': uid()})
        except (KeyError, TypeError, ValueError, zipfile.BadZipFile): self.reply(422, {'message': '请求内容或导入包无效'})
        except Exception:
            self.reply(500, {'message': '操作失败，原有内容保留', 'traceId': uid()})
    def body(self, limit=30 * 1024 * 1024):
        length = int(self.headers.get('Content-Length', '0'))
        if length > limit: raise Problem(413, '请求文件超过本地版大小限制')
        return self.rfile.read(length)
    def user(self, db):
        cookie = self.headers.get('Cookie', '')
        token = next((v.split('=', 1)[1] for v in cookie.split('; ') if v.startswith('session=')), '')
        row = db.execute('SELECT user_id FROM sessions WHERE token=? AND expires>?', (digest(token.encode()), time.time())).fetchone()
        if not row: raise Problem(401, '请先登录')
        return row[0]
    def course(self, db, cid, owner):
        c = db.execute('SELECT * FROM courses WHERE id=? AND owner=?', (cid, owner)).fetchone()
        if not c: raise Problem(403, '无权访问课程')
        return c
    def route(self, db):
        path = urlsplit(self.path).path
        method = self.command
        if not path.startswith('/v1/'):
            name = path.lstrip('/') or 'index.html'
            file = (ROOT / 'static' / name).resolve()
            if not file.is_relative_to((ROOT / 'static').resolve()) or not file.is_file(): raise Problem(404, '页面不存在')
            return self.reply(200, file.read_bytes(), {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8'}.get(file.suffix, 'application/octet-stream'))
        if method != 'GET':
            origin = self.headers.get('Origin')
            if origin and origin != ('https://' if os.environ.get('ZHIWEI_SECURE') else 'http://') + self.headers.get('Host', ''): raise Problem(403, '跨站请求被拒绝')
        if path in ('/v1/register', '/v1/login') and method == 'POST':
            d = json.loads(self.body()); email = d['email'].strip().lower(); password = d['password']
            if len(password) < 10 or '@' not in email: raise Problem(422, '请输入邮箱和至少 10 位密码')
            if path.endswith('register'):
                salt = secrets.token_hex(16)
                try: db.execute('INSERT INTO users VALUES(?,?,?,?)', (uid(), email, salt, hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()))
                except sqlite3.IntegrityError: raise Problem(409, '邮箱已注册')
            u = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if not u or not hmac.compare_digest(u['password'], hashlib.scrypt(password.encode(), salt=u['salt'].encode(), n=16384, r=8, p=1).hex()): raise Problem(401, '邮箱或密码错误')
            token = secrets.token_urlsafe(32)
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (digest(token.encode()), u['id'], time.time()+86400))
            return self.reply(200, {'email': email}, headers={'Set-Cookie': f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400' + ('; Secure' if os.environ.get('ZHIWEI_SECURE') else '')})
        if path.startswith('/v1/public/'):
            cid = path.split('/')[-1]
            c = db.execute('SELECT published FROM courses WHERE id=?', (cid,)).fetchone()
            if not c or not c[0]: raise Problem(404, '课程未发布或已撤回')
            r = db.execute('SELECT * FROM releases WHERE id=?', (c[0],)).fetchone()
            return self.reply(200, {'releaseId': r['id'], 'draft': json.loads(r['payload'])})
        if path.startswith('/v1/assets/') and method == 'GET':
            a = db.execute('SELECT * FROM assets WHERE id=?', (path.split('/')[-1],)).fetchone()
            if not a or db.execute('SELECT 1 FROM deleted_assets WHERE id=?',(a['id'],)).fetchone(): raise Problem(404, '素材不存在')
            c = db.execute('SELECT * FROM courses WHERE id=?', (a['course'],)).fetchone()
            public = False
            if c['published']:
                public = a['id'] in db.execute('SELECT payload FROM releases WHERE id=?', (c['published'],)).fetchone()[0]
            if not public: self.course(db, a['course'], self.user(db))
            raw = a['bytes']; headers = {'Accept-Ranges': 'bytes'}
            if self.headers.get('Range'):
                start, end = self.headers['Range'].removeprefix('bytes=').split('-'); start = int(start); end = int(end) if end else len(raw)-1
                if start < 0 or start > end or end >= len(raw): raise Problem(416, '无效 Range')
                headers['Content-Range'] = f'bytes {start}-{end}/{len(raw)}'
                return self.reply(206, raw[start:end+1], a['mime'], headers)
            return self.reply(200, raw, a['mime'], headers)
        owner = self.user(db)
        if path == '/v1/imports' and method == 'POST':
            raw = self.body()
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                entries = z.infolist()
                if len(entries) > 10000 or sum(i.file_size for i in entries) > 100*1024*1024: raise Problem(422, '导入包过大')
                if len({i.filename for i in entries}) != len(entries) or any('..' in i.filename or i.filename.startswith(('/', '\\')) or ':' in i.filename for i in entries): raise Problem(422, '非法文件路径')
                manifest = json.loads(z.read('manifest.json'))
                if manifest['formatVersion'] != 1: raise Problem(422, '不支持的导出版本')
                if set(manifest['files']) != {i.filename for i in entries} - {'manifest.json'}: raise Problem(422, '清单与文件集合不一致')
                for name, meta in manifest['files'].items():
                    content = z.read(name)
                    if len(content) != meta['size'] or digest(content) != meta['sha256']: raise Problem(422, '文件校验失败')
                d = json.loads(z.read('course.json')); check_shape(d)
                if validate(d): raise Problem(422, '课程存在无效引用或关系')
                assets = json.loads(z.read('asset-index.json'))
                package = {'draft':d, 'assets':[{**a, 'content':base64.b64encode(z.read('assets/'+a['id'])).decode()} for a in assets]}
                for a in package['assets']:
                    if digest(base64.b64decode(a['content'])) != a['checksum']: raise Problem(422, '素材校验失败')
                task = uid(); db.execute('INSERT INTO imports VALUES(?,?,?)', (task, owner, encode(package)))
                return self.reply(200, {'taskId':task, 'title':d['title'], 'nodes':len(d['nodes']), 'assets':len(assets)})
        if path.startswith('/v1/imports/') and method == 'POST':
            task = path.split('/')[-1]
            row = db.execute('SELECT payload FROM imports WHERE id=? AND owner=?', (task,owner)).fetchone()
            if not row: raise Problem(404, '导入任务不存在')
            package = json.loads(row[0])
            if 'courseId' in package: return self.reply(200, {'id':package['courseId']})
            mapping = {}
            def collect(v):
                if isinstance(v,dict):
                    for k,w in v.items():
                        if k in ('id','blockId','sectionId') and isinstance(w,str): mapping[w] = uid()
                        else: collect(w)
                elif isinstance(v,list):
                    for w in v: collect(w)
            collect(package)
            def rewrite(v):
                if isinstance(v,str): return mapping.get(v,v)
                if isinstance(v,list): return [rewrite(w) for w in v]
                if isinstance(v,dict): return {k:rewrite(w) for k,w in v.items()}
                return v
            imported = rewrite(package); cid = uid(); d = imported['draft']
            db.execute('INSERT INTO courses VALUES(?,?,?,?,?,NULL)', (cid,owner,d['title'],0,encode(d)))
            for a in imported['assets']: db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)', (a['id'],cid,a['name'],a['mime'],a['checksum'],base64.b64decode(a['content'])))
            db.execute('UPDATE imports SET payload=? WHERE id=?', (encode({'courseId':cid}),task))
            return self.reply(201, {'id':cid})
        if path == '/v1/me': return self.reply(200, {'id': owner, 'dataDirectory': str(DATA.resolve()), 'applicationVersion': 'backup-1'})
        if path == '/v1/logout':
            db.execute('DELETE FROM sessions WHERE user_id=?', (owner,))
            return self.reply(200, {}, headers={'Set-Cookie': 'session=; Max-Age=0; Path=/'})
        if path == '/v1/courses':
            if method == 'GET': return self.reply(200, [dict(r) for r in db.execute('SELECT id,title,revision,published FROM courses WHERE owner=?', (owner,))])
            d = json.loads(self.body()); cid = uid(); draft = {'schemaVersion': 1, 'title': d['title'], 'nodes': [], 'outline': [], 'relations': [], 'templates': []}
            db.execute('INSERT INTO courses VALUES(?,?,?,?,?,NULL)', (cid, owner, d['title'], 0, encode(draft)))
            return self.reply(201, {'id': cid})
        parts = path.split('/')
        if len(parts) < 4 or parts[2] != 'courses': raise Problem(404, '接口不存在')
        cid = parts[3]; c = self.course(db, cid, owner); action = parts[4] if len(parts)>4 else ''
        if not action: return self.reply(200, {'id': cid, 'revision': c['revision'], 'draft': json.loads(c['draft']), 'published': c['published']}, headers={'ETag': str(c['revision'])})
        if action == 'backup' and method == 'GET':
            db.execute('BEGIN')
            c = self.course(db, cid, owner)
            published = db.execute('SELECT payload FROM releases WHERE id=?', (c['published'],)).fetchone()
            files = {'course.json': c['draft'].encode(), 'backup.json': encode({'backupVersion':1, 'courseId':cid, 'published':json.loads(published[0]) if published else None}).encode()}
            assets = list(db.execute('SELECT * FROM assets WHERE course=? AND id NOT IN (SELECT id FROM deleted_assets)', (cid,)))
            files['asset-index.json'] = encode([{k:a[k] for k in ('id','name','mime','checksum')} for a in assets]).encode()
            for a in assets: files['assets/'+a['id']] = a['bytes']
            manifest = {'formatVersion':1, 'files':{k:{'size':len(v),'sha256':digest(v)} for k,v in files.items()}}
            stream = io.BytesIO()
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                for k,v in files.items(): z.writestr(k,v)
                z.writestr('manifest.json',encode(manifest))
            return self.reply(200,stream.getvalue(),'application/zip',{'Content-Disposition':'attachment; filename="course-backup.zip"'})
        if action == 'restore' and method == 'POST':
            with zipfile.ZipFile(io.BytesIO(self.body(512*1024*1024))) as z:
                entries = z.infolist()
                if len(entries)>10000 or sum(i.file_size for i in entries)>1024*1024*1024: raise Problem(422,'备份包过大')
                if len({i.filename for i in entries})!=len(entries) or any('..' in i.filename or i.filename.startswith(('/', '\\')) or ':' in i.filename for i in entries): raise Problem(422,'非法备份路径')
                manifest = json.loads(z.read('manifest.json'))
                if manifest['formatVersion']!=1 or set(manifest['files'])!={i.filename for i in entries}-{'manifest.json'}: raise Problem(422,'备份清单无效')
                for name,meta in manifest['files'].items():
                    raw = z.read(name)
                    if len(raw)!=meta['size'] or digest(raw)!=meta['sha256']: raise Problem(422,'备份文件校验失败')
                meta = json.loads(z.read('backup.json'))
                if meta['backupVersion']!=1 or meta['courseId']!=cid: raise Problem(422,'请选择当前课程的本地备份文件')
                d = json.loads(z.read('course.json')); check_shape(d)
                published = meta['published']
                if published is not None:
                    check_shape(published)
                    if validate(published): raise Problem(422,'备份中的学生发布版无效')
                assets = json.loads(z.read('asset-index.json')); ids = set(); media = []
                for a in assets:
                    if not isinstance(a['id'],str) or not a['id'] or a['id'] in ids: raise Problem(422,'备份素材标识无效')
                    raw = z.read('assets/'+a['id'])
                    if digest(raw)!=a['checksum']: raise Problem(422,'备份素材校验失败')
                    ids.add(a['id']); media.append((a,raw))
                for payload in [d,published]:
                    if payload is None: continue
                    for n in payload['nodes']+payload['templates']:
                        for section in n['sections']:
                            for b in section['blocks']:
                                if b['type'] in ('image','video','attachment') and b['data'].get('assetId') not in ids: raise Problem(422,'备份缺少课程素材')
            db.execute('BEGIN IMMEDIATE')
            c = self.course(db,cid,owner)
            if self.headers.get('If-Match')!=str(c['revision']): raise Problem(412,'草稿已变化，请重新加载后再恢复')
            for a,raw in media:
                existing = db.execute('SELECT course,checksum FROM assets WHERE id=?',(a['id'],)).fetchone()
                if existing and (existing['course']!=cid or existing['checksum']!=a['checksum']): raise Problem(422,'备份素材与现有数据冲突')
            db.execute('INSERT OR REPLACE INTO deleted_assets SELECT id,course,? FROM assets WHERE course=?',(time.time(),cid))
            for a,raw in media:
                db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?)',(a['id'],cid,a['name'],a['mime'],a['checksum'],raw))
                db.execute('DELETE FROM deleted_assets WHERE id=?',(a['id'],))
            rid = None
            if published is not None:
                rid = uid(); payload = encode(published)
                db.execute('INSERT INTO releases VALUES(?,?,?,?,?)',(rid,cid,payload,digest(payload.encode()),time.time()))
            revision = c['revision']+1
            db.execute('UPDATE courses SET draft=?,title=?,revision=?,published=? WHERE id=?',(encode(d),d['title'],revision,rid,cid))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(uid(),cid,revision,encode(d),time.time()))
            return self.reply(200,{'revision':revision,'restored':True})
        if action == 'draft' and method == 'PUT':
            d = json.loads(self.body()); check_shape(d)
            expected = self.headers.get('If-Match')
            revision = c['revision'] + 1
            result = db.execute('UPDATE courses SET draft=?,title=?,revision=? WHERE id=? AND revision=?', (encode(d), d['title'], revision, cid, expected))
            if result.rowcount != 1: raise Problem(412, '版本冲突，已保留本地副本，请下载副本后重新加载并合并')
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?)', (uid(), cid, revision, encode(d), time.time()))
            return self.reply(200, {'revision': revision, 'savedAt': time.time()}, headers={'ETag': str(revision)})
        if action == 'validate': return self.reply(200, validate(json.loads(c['draft'])))
        if action == 'releases':
            if method == 'GET': return self.reply(200, [dict(r) for r in db.execute('SELECT id,hash,created FROM releases WHERE course=? ORDER BY created DESC', (cid,))])
            if self.headers.get('If-Match') != str(c['revision']): raise Problem(412, '草稿版本已变化')
            d = json.loads(c['draft']); errors = validate(d)
            for n in d['nodes']:
                for s in n['sections']:
                    for b in s['blocks']:
                        if b['type'] in ('image', 'video', 'attachment') and not db.execute('SELECT 1 FROM assets WHERE id=? AND course=? AND id NOT IN (SELECT id FROM deleted_assets)', (b['data'].get('assetId'), cid)).fetchone(): errors.append({'nodeId': n['id'], 'message': '素材未就绪'})
            if errors: return self.reply(422, {'message': '发布检查失败', 'issues': errors})
            rid = uid(); db.execute('INSERT INTO releases VALUES(?,?,?,?,?)', (rid, cid, c['draft'], digest(c['draft'].encode()), time.time()))
            db.execute('UPDATE courses SET published=? WHERE id=?', (rid, cid))
            return self.reply(201, {'releaseId': rid})
        if action == 'activate':
            rid = json.loads(self.body()).get('releaseId')
            if rid and not db.execute('SELECT 1 FROM releases WHERE id=? AND course=?', (rid,cid)).fetchone(): raise Problem(422, '历史版本无效')
            db.execute('UPDATE courses SET published=? WHERE id=?', (rid, cid)); return self.reply(200, {})
        if action == 'assets':
            if method == 'GET':
                return self.reply(200, [{**dict(r), 'name': asset_name(r['name'], r['mime'])} for r in db.execute('SELECT id,name,mime,checksum FROM assets WHERE course=? AND id NOT IN (SELECT id FROM deleted_assets)', (cid,))])
            if method == 'PUT' and len(parts) == 6:
                name = json.loads(self.body())['name'].strip()
                if not name or len(name) > 200: raise Problem(422, '请输入 1 至 200 字的素材名称')
                result = db.execute('UPDATE assets SET name=? WHERE id=? AND course=?', (name, parts[5], cid))
                if result.rowcount != 1: raise Problem(404, '素材不存在')
                return self.reply(200, {'name': name})
            if method == 'DELETE' and len(parts) == 6:
                aid = parts[5]
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM assets WHERE id=? AND course=?', (aid,cid)).fetchone(): raise Problem(404, '素材不存在')
                c = self.course(db,cid,owner)
                if self.headers.get('If-Match') != str(c['revision']): raise Problem(412,'草稿已变化，请重新加载后再删除素材')
                def detach(payload):
                    data = json.loads(payload)
                    removed = set()
                    for node in data.get('nodes', []) + data.get('templates', []):
                        for section in node.get('sections', []):
                            removed.update(b['blockId'] for b in section['blocks'] if b['type'] in ('image','video','attachment') and b.get('data',{}).get('assetId')==aid)
                            section['blocks'] = [b for b in section['blocks'] if b['blockId'] not in removed]
                    for node in data.get('nodes',[]) + data.get('templates',[]):
                        for section in node['sections']:
                            for block in section['blocks']:
                                if block['type']=='reference' and block['data'].get('anchor') in removed: block['data']['anchor']=''
                    return encode(data)
                draft = detach(c['draft']); rid = c['published']
                if rid:
                    original = db.execute('SELECT payload FROM releases WHERE id=?',(rid,)).fetchone()[0]
                    cleaned = detach(original)
                    if cleaned != original:
                        rid = uid(); db.execute('INSERT INTO releases VALUES(?,?,?,?,?)',(rid,cid,cleaned,digest(cleaned.encode()),time.time()))
                revision = c['revision']+1
                db.execute('UPDATE courses SET draft=?,revision=?,published=? WHERE id=?',(draft,revision,rid,cid))
                db.execute('INSERT INTO revisions VALUES(?,?,?,?,?)',(uid(),cid,revision,draft,time.time()))
                # Retain bytes internally; user-visible rollback now uses local backups.
                db.execute('INSERT OR IGNORE INTO deleted_assets VALUES(?,?,?)',(aid,cid,time.time()))
                return self.reply(200, {'deleted':True,'revision':revision,'draft':json.loads(draft)})
            raw = self.body(); mime = self.headers.get('Content-Type'); aid = uid()
            valid = (mime == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')) or (mime == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff')) or (mime == 'video/mp4' and raw[4:8] == b'ftyp')
            if not valid: raise Problem(422, '只支持 PNG、JPEG 和 MP4；文件签名不匹配')
            name = asset_name(self.headers.get('X-Filename',''), mime)
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)', (aid,cid,name,mime,digest(raw),raw))
            return self.reply(201, {'id': aid, 'name': name, 'mime': mime, 'checksum': digest(raw)})
        if action == 'export':
            stream = io.BytesIO(); files = {'course.json': c['draft'].encode()}
            for a in db.execute('SELECT * FROM assets WHERE course=? AND id NOT IN (SELECT id FROM deleted_assets)', (cid,)): files['assets/'+a['id']] = a['bytes']
            files['asset-index.json'] = encode([dict(r) for r in db.execute('SELECT id,name,mime,checksum FROM assets WHERE course=? AND id NOT IN (SELECT id FROM deleted_assets)', (cid,))]).encode()
            files['releases.json'] = encode([dict(r) for r in db.execute('SELECT * FROM releases WHERE course=?', (cid,))]).encode()
            manifest = {'formatVersion':1, 'files':{k:{'size':len(v),'sha256':digest(v)} for k,v in files.items()}}
            with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
                for k,v in files.items(): z.writestr(k,v)
                z.writestr('manifest.json',encode(manifest))
            return self.reply(200,stream.getvalue(),'application/zip',{'Content-Disposition':'attachment; filename="course.zip"'})
        raise Problem(404, '接口不存在')

class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False
    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

def main(open_browser=True):
    port = int(os.environ.get('PORT', '4180'))
    url = f'http://127.0.0.1:{port}'
    try:
        service = LocalServer(('127.0.0.1', port), Handler)
    except OSError as error:
        print(f'Cannot start Zhiwei: {error}\nIf already running, open {url}. Otherwise set PORT to another free port.', flush=True)
        raise SystemExit(1)
    print(f'Zhiwei is running: {url}\nData directory: {DATA.resolve()}\nOpen this URL in your browser. Keep this window open. Press Ctrl+C to stop.', flush=True)
    if open_browser:
        try: webbrowser.open(url)
        except webbrowser.Error: print('Please open the URL above manually.', flush=True)
    try:
        service.serve_forever()
    except KeyboardInterrupt:
        print('\nZhiwei stopped.', flush=True)
    finally:
        service.server_close()
if __name__ == '__main__': main(open_browser='--no-browser' not in sys.argv)
