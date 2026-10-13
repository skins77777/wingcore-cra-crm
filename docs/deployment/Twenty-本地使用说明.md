# Twenty 本地使用说明

项目目录：`K:\CRA客户项目`。本说明对应本机专用 WSL 发行版 `CRA-Ubuntu-24.04` 和 Compose 项目 `cra-twenty`。

## 访问与日常操作

本机访问地址：<http://localhost:3000>。

| 操作 | 项目根目录入口 |
| --- | --- |
| 启动 / 重启电脑后恢复服务 | 双击 `Start-Twenty.cmd`，等待健康检查完成 |
| 停止 CRM | 双击 `Stop-Twenty.cmd`；保留数据库和附件 |
| 备份 | 双击 `Backup-Twenty.cmd`；会短暂停止网页和 worker，结束后恢复原先运行的服务 |

本次不设置登录自动启动。Windows 关机、休眠或停止 WSL 时 CRM 不能使用。启动脚本会保留一个后台 WSL 会话，避免服务因会话空闲退出。停止入口只停止 CRM 容器，不删除数据、不关闭 Windows 代理。

命令行查看状态：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "K:\CRA客户项目\scripts\Manage-Twenty.ps1" -Action Status
```

管理入口只为当前 PowerShell 进程使用 RemoteSigned，不修改电脑的全局执行策略。发行版注册在当前 Windows 用户下；请使用本次部署的 Windows 账户运行。

## 首次使用

首次账户、密码和工作区名称由使用者自行设置。本次最终观察时，浏览器已进入“邀请您的团队”步骤；个人使用可跳过团队邀请后进入工作区。账户信息由使用者填写，代理未读取或设置使用者密码。工作区内业务操作需要在完成向导后验证。

当前邮件驱动为 logger，尚未配置 SMTP；邮件邀请、邮件验证码送达和邮件找回密码不能视为可用。Google / Microsoft 邮箱、聊天、模型 API 和 CRA 业务规则均未配置。

## 软件和数据位置

- Ubuntu 24.04.5 LTS，WSL 2。
- Docker Engine 29.9.0，Docker Compose 5.6.0。
- Twenty server / worker 同版本 `v2.45.0`，来源为官方 `twenty/v2.45.0` 发布。
- PostgreSQL 16、Redis 7.4；具体镜像摘要在最终部署验收记录中保存。
- 正式配置：`deployment/twenty/compose.yaml`、`deployment/twenty/.env`，以及拉取后生成的镜像锁定覆盖文件。
- 官方原始配置：`deployment/twenty/upstream/`；发布提交和原文件校验值：`deployment/twenty/provenance.json`。
- Linux / Docker 运行数据：`runtime/wsl/CRA-Ubuntu-24.04/ext4.vhdx`。数据库、附件和 Redis 卷实际位于此虚拟磁盘内部。
- 卷名：`cra-twenty_db-data`、`cra-twenty_server-local-data`、`cra-twenty_redis-data`。
- 业务记录和导出资料：`records/`。
- 备份：`backups/`。

`.env` 内有本实例随机生成的数据库密码和加密密钥。文件和备份目录的 Windows 权限已限制给当前用户、SYSTEM 和管理员组。不要把密钥发到聊天、提交到 Git 或丢弃；数据库和对应密钥要一起保留。`.gitignore` 已排除密钥、运行磁盘、业务记录和备份。

运行中不要移动项目目录或直接复制正在使用的 VHDX 作为数据库备份。日常使用备份入口导出数据库和附件。

## 本机网络配置

网页端口只绑定 `127.0.0.1:3000`，数据库和 Redis 不开放主机端口。未配置公网访问、VPS 或 SSH。

本机直连 Docker Hub 超时；现有 Windows HTTP 代理为 `127.0.0.1:10808`。由于本机禁用了 IPv6 的系统组件，WSL 镜像网络模式不可用，最终使用 NAT 模式并配置了项目专用代理转接：

- `scripts/wsl-image-proxy.py` 只监听 WSL 虚拟网卡的主机地址、端口 18080。
- 转接程序只接受本项目 WSL 当前 IP 的连接，转发到既有 `127.0.0.1:10808`。
- Windows 防火墙规则 `CRA-Twenty-WSL-ImageProxy` 同时限制本地地址、远端 WSL IP 和端口。
- `scripts/Start-ImageProxy.ps1` 随启动入口运行，刷新 WSL 地址并配置 Docker 的镜像下载代理。
- 镜像下载和更新需要原有 Windows 代理可用；已有本地 CRM 容器运行不依赖外网代理。
- WSL 全局设置位于 `C:\Users\Administrator\.wslconfig`，项目留存副本在 `deployment/wsl/.wslconfig`。实际设置为 `networkingMode=nat`、`autoProxy=false`。
- Docker 守护程序配置位于该发行版 `/etc/docker/daemon.json`，模板保存在 `deployment/wsl/docker-daemon.json`，实际动态地址副本保存在 `runtime/docker-daemon.json`。
- Twenty server / worker 的外部 HTTP 访问同样使用项目代理；内部数据库、Redis 及本机访问排除代理，NPM 读取实测返回 200。

没有修改 Windows 原有代理设置或 IPv6 设置，也没有放开局域网 / 公网访问。

## 备份与恢复材料

每个时间戳备份目录包含：

- `database.dump`：PostgreSQL 自定义格式备份。
- `uploads.tar.gz`：共享附件卷内容。
- `.env`、Compose 配置及镜像锁定文件。
- `images.json`：当时的镜像记录。
- `SHA256SUMS`：关键备份文件校验值。
- `database-contents.txt`：数据库备份对象列表。

恢复需要同时恢复数据库、附件和对应 `.env`，并使用记录的版本。恢复会覆盖目标数据，先检查目标实例和当前备份，再执行恢复。备份存放在同一块 K 盘，不能防范整块磁盘损坏；后续可另设用户指定位置的副本。

## 当前验收进度

基础部署验收已通过：数据库、Redis、网页健康检查正常，worker 已实际处理定时任务；浏览器显示首次注册页面。已验证停止 / WSL 环境重启 / 启动后的恢复，以及数据库表持久化（75 张表）。首份数据库备份已恢复到临时数据库并比对通过，临时数据库已清理。

管理员首次注册、工作区业务操作、附件上传下载和 CRA 自动化配置尚未验收；这些步骤在使用者初始化账户及明确业务规则后继续。

CRA v0.3.5 的 `cra-setup`、`crm-fde`、`chat-signal` 已安装在项目 `.agents/skills/`，共 80 个文件，源文件校验全部一致。
