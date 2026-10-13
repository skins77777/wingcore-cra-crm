# Wingcore 本地 WhatsApp 接入

配置来源：Evolution 官方 2.3.7 发布及同标签的 docker-compose.yaml/.env.example。
使用独立 Compose 项目 cra-evolution、独立数据库/缓存/会话卷，不修改 Twenty 数据库。
API 只绑定 127.0.0.1:8082（原8080被已有node进程占用）。未配置公网入口、模型或 CRM 写入。
该版本CORS中间件拒绝无Origin的普通页面导航，采用官方通配Origin配置并禁用浏览器凭据；业务API仍须密钥鉴权，密钥不可写入公共页面。
镜像已固定为 evoapicloud/evolution-api@sha256:1bd8afc4a6cf48822e6cf02469aeae7bd35a12a6b616eacd1291926307f4d339，版本2.3.7。

2026-10-11二维码空白修复：容器直连web.whatsapp.com超时，复用本机原有代理转发172.22.176.1:18080（转至Windows127.0.0.1:10808）。配置PROXY_HOST/PORT/PROTOCOL供Baileys连接，另配HTTP_PROXY/HTTPS_PROXY供启动时网页版本查询；NO_PROXY排除内部服务。经代理WhatsApp HTTP200，修复后instance/connect实际返回base64二维码且count=1。没有发送消息或完成手机关联。
若WSL重启更换网关，需核对runtime/image-proxy-state.json并更新此私密.env中的代理地址，重建api容器；不可盲目沿用旧网关。现有转发器需保持运行。

私密 .env 中的随机数据库密码和 API key 已生成，并限制为当前 Windows 用户及 SYSTEM 访问。不要把这些值贴进聊天、截图或版本库。

WSL 管理命令（在项目路径下运行）：

```powershell
wsl.exe -d CRA-Ubuntu-24.04 -u root --cd '/mnt/k/CRA客户项目/deployment/evolution' -- docker compose up -d
wsl.exe -d CRA-Ubuntu-24.04 -u root --cd '/mnt/k/CRA客户项目/deployment/evolution' -- docker compose ps
```

仅下载镜像或服务启动不代表 WhatsApp 账号已连接。手机关联已核实号码及双向消息；2026-10-12已补充本地持续采集，见[采集说明](collector.md)。模型实时分析与 CRM 自动写入仍未上线。

数据卷不要删除；后续备份须包含数据库和实例会话。固定镜像摘要在下载后登记，升级前核实官方变更并验证。
