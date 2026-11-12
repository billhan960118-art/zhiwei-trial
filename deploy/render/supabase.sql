-- Apply once to the dedicated free test project, never to the local SQLite DB.
CREATE SCHEMA IF NOT EXISTS zhiwei;
REVOKE ALL ON SCHEMA zhiwei FROM PUBLIC, anon, authenticated;
CREATE TABLE IF NOT EXISTS zhiwei.users(id TEXT PRIMARY KEY,email TEXT UNIQUE,salt TEXT,password TEXT);
CREATE TABLE IF NOT EXISTS zhiwei.sessions(token TEXT PRIMARY KEY,user_id TEXT,expires DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS zhiwei.courses(id TEXT PRIMARY KEY,owner TEXT,title TEXT,revision INTEGER,draft TEXT,published TEXT);
CREATE TABLE IF NOT EXISTS zhiwei.revisions(id TEXT PRIMARY KEY,course TEXT,revision INTEGER,payload TEXT,created DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS zhiwei.releases(id TEXT PRIMARY KEY,course TEXT,payload TEXT,hash TEXT,created DOUBLE PRECISION);
-- bytes stores a private Storage object key, not binary content.
CREATE TABLE IF NOT EXISTS zhiwei.assets(id TEXT PRIMARY KEY,course TEXT,name TEXT,mime TEXT,checksum TEXT,bytes TEXT);
CREATE TABLE IF NOT EXISTS zhiwei.asset_objects(key TEXT PRIMARY KEY,size BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS zhiwei.deleted_assets(id TEXT PRIMARY KEY,course TEXT,deleted_at DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS zhiwei.imports(id TEXT PRIMARY KEY,owner TEXT,payload TEXT);
CREATE TABLE IF NOT EXISTS zhiwei.feedback(id TEXT PRIMARY KEY,category TEXT,description TEXT,steps TEXT,contact TEXT,page TEXT,created DOUBLE PRECISION);
CREATE INDEX IF NOT EXISTS courses_owner ON zhiwei.courses(owner);
CREATE INDEX IF NOT EXISTS assets_course ON zhiwei.assets(course);
CREATE INDEX IF NOT EXISTS releases_course ON zhiwei.releases(course);
-- No browser/client policy is granted for this private bucket.
INSERT INTO storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
VALUES('zhiwei-media','zhiwei-media',false,10485760,ARRAY['image/png','image/jpeg','video/mp4'])
ON CONFLICT(id) DO NOTHING;
