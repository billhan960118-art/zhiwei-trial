"""Gunicorn WSGI entrypoint; reuses the tested local API without a second HTTP server."""
import io
import json
from pathlib import Path
from urllib.parse import urlsplit
from zhiwei import server

ROOT=Path(__file__).parent
if server.os.environ.get('ZHIWEI_BACKEND')=='supabase':
    from .supabase_backend import connect
    server.connect=connect


class Socket:
    def __init__(self,raw): self.input=io.BytesIO(raw);self.output=bytearray()
    def makefile(self,*args,**kwargs): return self.input
    def sendall(self,data): self.output.extend(data)

class Handler(server.Handler):
    def body(self,limit=30*1024*1024):
        if server.os.environ.get('ZHIWEI_BACKEND')=='supabase':
            limit=min(limit,40*1024*1024)
            if '/assets' in urlsplit(self.path).path and self.command=='POST':limit=min(limit,10*1024*1024)
        return super().body(limit)
    def route(self,db):
        path=urlsplit(self.path).path
        if path=='/v1/me' and server.os.environ.get('ZHIWEI_BACKEND')=='supabase':
            return self.reply(200,{'id':self.user(db),'dataDirectory':'云端独立测试数据','applicationVersion':'render-supabase-trial-1'})
        if path=='/healthz': return self.reply(200,{'status':'ok','version':'render-trial-1'})
        if path=='/v1/public/demo': return self.reply(200,{'releaseId':'demo-v1','draft':json.loads((ROOT/'sample.json').read_text(encoding='utf-8'))})
        if path=='/feedback.js': return self.reply(200,(ROOT/'static/feedback.js').read_bytes(),'text/javascript; charset=utf-8')
        if path=='/':
            html=(server.ROOT/'static/index.html').read_text(encoding='utf-8').replace('</body>','<script type="module" src="feedback.js"></script></body>')
            return self.reply(200,html.encode(),'text/html; charset=utf-8')
        if path=='/v1/feedback' and self.command=='POST':
            origin=self.headers.get('Origin')
            expected=('https://' if server.os.environ.get('ZHIWEI_SECURE') else 'http://')+self.headers.get('Host','')
            if origin and origin!=expected: raise server.Problem(403,'跨站请求被拒绝')
            raw=self.body(12000);d=json.loads(raw)
            if not isinstance(d.get('description'),str) or len(d['description'].strip())<5: raise server.Problem(422,'请至少填写 5 个字的反馈')
            db.execute('CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,category TEXT,description TEXT,steps TEXT,contact TEXT,page TEXT,created REAL)')
            count=db.execute('SELECT count(*) FROM feedback WHERE created>?',(server.time.time()-86400,)).fetchone()[0]
            if count>=1000: raise server.Problem(429,'今日反馈较多，请稍后再试')
            ident=server.uid();db.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?,?)',(ident,str(d.get('category','使用问题'))[:40],d['description'][:4000],str(d.get('steps',''))[:3000],str(d.get('contact',''))[:200],str(d.get('page',''))[:300],server.time.time()))
            return self.reply(201,{'id':ident})
        return super().route(db)

def application(environ,start_response):
    try: length=int(environ.get('CONTENT_LENGTH') or '0')
    except ValueError: length=-1
    if length<0 or length>512*1024*1024:
        start_response('413 Payload Too Large',[('Content-Type','application/json')]);return [b'{"message":"Request too large"}']
    path=environ.get('PATH_INFO','/')
    if environ.get('QUERY_STRING'): path+='?'+environ['QUERY_STRING']
    headers=[]
    for k,v in environ.items():
        if k.startswith('HTTP_'): headers.append((k[5:].replace('_','-'),v))
    if environ.get('CONTENT_TYPE'):headers.append(('Content-Type',environ['CONTENT_TYPE']))
    headers.append(('Content-Length',str(length)))
    raw=(environ['REQUEST_METHOD']+' '+path+' HTTP/1.0\r\n'+''.join(k+': '+v+'\r\n' for k,v in headers)+'\r\n').encode('iso-8859-1')+environ['wsgi.input'].read(length)
    sock=Socket(raw);Handler(sock,(environ.get('REMOTE_ADDR','127.0.0.1'),0),None)
    head,body=bytes(sock.output).split(b'\r\n\r\n',1);lines=head.decode('iso-8859-1').split('\r\n')
    out=[tuple(line.split(': ',1)) for line in lines[1:] if line and line.split(':',1)[0].lower() not in ('connection','transfer-encoding')]
    start_response(lines[0].split(' ',1)[1],out);return [body]
