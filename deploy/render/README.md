# Render + Supabase 免费测试版

Render：免费实例，无磁盘。Supabase：独立免费项目 jmiknozmjjnybmzjjwwv，新加坡区域。数据库、会话、发布内容、反馈位于私有 zhiwei schema；素材保存在私有 zhiwei-media 桶。本机默认 SQLite 不受影响。

首次连接需通过 Render Environment 配置 DATABASE_URL（Supabase Connect 中的 Session pooler URL）、SUPABASE_SERVICE_ROLE_KEY。不要把密钥放进聊天、Git、前端或日志。SUPABASE_URL 为 https://jmiknozmjjnybmzjjwwv.supabase.co，桶名为 zhiwei-media。

schema 初始化使用 supabase.sql，已在空测试项目应用。应用缺少凭据时失败关闭，不回退到 Render 临时文件系统。PostgreSQL 兼容层保留原课程 API；媒体以不可变对象键保存在 Storage。为初期小规模测试，数据库请求按事务串行化以保持原备份恢复的并发语义，不能视为大规模并发方案。

免费额度保护：单素材 10 MB，素材元数据已计入总量达到 700 MB 后拒绝新上传；备份恢复请求限制 40 MB。软删除不物理释放历史对象。Supabase 与 Render 的平台额度、休眠和暂停仍然适用，额度内免费不代表无限使用。

验证：python -m unittest tests.test_supabase_backend tests.test_render_adapter；后端原 18 项回归与根目录测试；隔离 WSGI 浏览器验证注册、创作、保存、发布、备份恢复与素材删除。真实 PostgreSQL/Storage 读写及公网验收需配置服务器凭据并完成部署后执行，不能将本地模拟测试视为线上验收。
