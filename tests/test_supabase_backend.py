import unittest
from unittest.mock import MagicMock,patch
from deploy.render.supabase_backend import Row,Connection,Storage,postgres_sql
from zhiwei import server

class SupabaseBackendTest(unittest.TestCase):
 def test_sql_translation_preserves_values_and_upserts(self):
  sql,media=postgres_sql('UPDATE courses SET draft=? WHERE id=? AND revision=?')
  self.assertEqual(sql,'UPDATE courses SET draft=%s WHERE id=%s AND revision=%s');self.assertFalse(media)
  self.assertIn('ON CONFLICT DO NOTHING',postgres_sql('INSERT OR IGNORE INTO deleted_assets VALUES(?,?,?)')[0])
  self.assertIn('ON CONFLICT(id) DO UPDATE',postgres_sql('INSERT OR REPLACE INTO assets VALUES(?,?,?,?,?,?)')[0])
  self.assertIn('ON CONFLICT(id) DO UPDATE',postgres_sql('INSERT OR REPLACE INTO deleted_assets SELECT id,course,? FROM assets WHERE course=?')[0])
  self.assertEqual(postgres_sql('BEGIN IMMEDIATE')[0],'SELECT pg_advisory_xact_lock(741806129)')
 def test_private_media_is_lazy_and_uses_immutable_keys(self):
  storage=MagicMock();storage.get.return_value=b'picture';row=Row({'id':'a','bytes':'course/a/hash'},storage)
  self.assertEqual(row[0],'a');storage.get.assert_not_called();self.assertEqual(row['bytes'],b'picture');self.assertEqual(row['bytes'],b'picture');storage.get.assert_called_once_with('course/a/hash')
  self.assertEqual(dict(row),{'id':'a','bytes':b'picture'})
  db=MagicMock();db.execute.return_value.fetchone.side_effect=[None,{'size':0}]
  conn=Connection(db,storage);conn.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',('asset','course','中文图','image/png','hash',b'picture'))
  storage.put.assert_called_once_with('course/asset/hash',b'picture','image/png');self.assertEqual(db.execute.call_args.args[1][-1],'course/asset/hash')
 def test_failed_requests_rollback_and_errors_do_not_leak_credentials(self):
  db=MagicMock();conn=Connection(db,MagicMock())
  with self.assertRaises(ValueError):
   with conn:raise ValueError('invalid')
  db.rollback.assert_called_once();db.commit.assert_not_called()
  with conn:pass
  db.commit.assert_called_once()
  with patch.dict('os.environ',{'SUPABASE_URL':'http://insecure.test','SUPABASE_SERVICE_ROLE_KEY':'secret'}):
   with self.assertRaises(RuntimeError):Storage()
 def test_free_tier_media_limits_fail_before_storage_write(self):
  db=MagicMock();storage=MagicMock();conn=Connection(db,storage)
  with self.assertRaises(server.Problem):conn.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',('a','c','图','image/png','hash',b'x'*(10*1024*1024+1)))
  storage.put.assert_not_called()
  db.execute.return_value.fetchone.side_effect=[None,{'size':700*1024*1024}]
  with self.assertRaises(server.Problem):conn.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',('a','c','图','image/png','hash',b'x'))
  storage.put.assert_not_called()
if __name__=='__main__':unittest.main()
