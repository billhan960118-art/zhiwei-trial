import io,json,tempfile,unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from deploy.render.app import application
from zhiwei import server

class RenderAdapterTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.original=server.DATA;server.DATA=Path(self.temp.name)
 def tearDown(self):server.DATA=self.original;self.temp.cleanup()
 def request(self,path,method='GET',data=None,cookie='',revision=None,origin=None):
  raw=json.dumps(data).encode() if data is not None else b'';env={'REQUEST_METHOD':method,'PATH_INFO':path,'QUERY_STRING':'','SERVER_NAME':'test','SERVER_PORT':'80','HTTP_HOST':'test','wsgi.input':io.BytesIO(raw),'CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','HTTP_COOKIE':cookie}
  if revision is not None:env['HTTP_IF_MATCH']=str(revision)
  if origin:env['HTTP_ORIGIN']=origin
  result={};body=b''.join(application(env,lambda status,headers:result.update(status=int(status.split()[0]),headers=dict(headers))))
  return result,json.loads(body) if body else None
 def test_auth_save_publish_feedback_and_storage(self):
  self.assertEqual(self.request('/healthz')[0]['status'],200)
  self.assertEqual(len(self.request('/v1/public/demo')[1]['draft']['nodes']),4)
  r,_=self.request('/v1/register','POST',{'email':'trial@test.org','password':'testing-password'});cookie=r['headers']['Set-Cookie'].split(';')[0];self.assertEqual(r['status'],200)
  _,course=self.request('/v1/courses','POST',{'title':'在线课程'},cookie);cid=course['id']
  _,saved=self.request('/v1/courses/'+cid,cookie=cookie);draft=saved['draft'];draft['nodes']=[{'id':'n','title':'知识点','tags':[],'sections':[]}]
  self.assertEqual(self.request('/v1/courses/'+cid+'/draft','PUT',draft,cookie,0)[0]['status'],200)
  self.assertEqual(self.request('/v1/courses/'+cid+'/draft','PUT',draft,cookie,0)[0]['status'],412)
  self.assertEqual(self.request('/v1/courses/'+cid+'/releases','POST',{},cookie,1)[0]['status'],201)
  self.assertEqual(self.request('/v1/public/'+cid)[1]['draft'],draft)
  self.assertEqual(self.request('/v1/feedback','POST',{'description':'公开测试反馈持久保存'})[0]['status'],201)
  self.assertEqual(self.request('/v1/feedback','POST',{'description':'跨站写入测试'},origin='https://evil.example')[0]['status'],403)
  with closing(server.connect()) as db:self.assertEqual(db.execute('select count(*) from feedback').fetchone()[0],1)
 def test_secure_cookie_and_csrf(self):
  with patch.dict(server.os.environ,{'ZHIWEI_SECURE':'1'}):
   r,_=self.request('/v1/register','POST',{'email':'secure@test.org','password':'testing-password'},origin='https://test');self.assertIn('Secure',r['headers']['Set-Cookie'])
   self.assertEqual(self.request('/v1/register','POST',{'email':'other@test.org','password':'testing-password'},origin='http://test')[0]['status'],403)
if __name__=='__main__':unittest.main()
