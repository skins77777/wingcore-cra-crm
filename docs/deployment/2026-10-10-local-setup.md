# 本地部署环境检查与准备

日期：2026-10-10（Asia/Hong_Kong）。项目：`K:\CRA客户项目`。

## 当前状态

**Twenty CRM v2.45.0 已本地部署，基础服务与网页验收通过；CRA Skill v0.3.5 文件已安装。使用者的首次向导已进入“邀请您的团队”步骤，业务规则尚待配置。**

用户已授权检查本地部署环境、补齐缺失项并在条件满足后安装所需软件。本轮已完成重启前的基础准备，未自动重启电脑。

## 环境检查结果

| 项目 | 检查结果 |
| --- | --- |
| Windows | Windows 11 专业版 22H2，版本 10.0.22621.4317 |
| CPU | Intel Core i9-13900KS，32 个逻辑处理器 |
| 内存 | 可见物理内存约 31.8 GiB；检查时可用约 4.9 GiB，实际可用量会变化 |
| 项目磁盘 | K 盘 NTFS，准备前可用约 211.8 GiB |
| 硬件虚拟化 | BIOS 已开启；CPU 支持 SLAT |
| 工具权限 | 当前 PowerShell 进程具备管理员权限，项目文件可读写 |
| 原有软件 | Git、winget、curl、Node.js、Python 已可定位；Docker 未安装 |
| 初始虚拟化状态 | VirtualMachinePlatform 未启用；hypervisorlaunchtype 为 Off；HypervisorPresent 为 false |

Twenty 官方 Docker Compose 部署指南要求至少 2 GB 内存及 Docker / Docker Compose。硬件满足基础要求，实际容器运行仍需后续验证。

最新版 Docker Desktop 要求 Windows 11 23H2（22631）或更高，本机 22H2 不满足。采用 WSL 2 + Ubuntu 24.04 LTS + Docker Engine / Docker Compose 的本地方案；不升级 Windows，不安装不兼容的 Docker Desktop。

## 本轮已完成的更改

1. 已启用 Windows `VirtualMachinePlatform`，明确使用 `NoRestart`。系统返回 `RestartNeeded: true`。
2. 将当前启动项 `hypervisorlaunchtype` 从 `Off` 改为 `Auto`，下次开机启动虚拟化管理程序。原值和新值均已记录；其他启动配置未修改。
3. 从 Microsoft / WSL 官方 GitHub 发布页下载并安装 WSL 3.0.1.0 x64。安装器返回 0；未自动重启。
4. `wsl --version` 已通过，报告 WSL 3.0.1.0、Linux 内核包 6.18.40.1-1。版本查询成功不代表 Linux 虚拟机已启动。
5. 已下载 Ubuntu 24.04.5 LTS 官方 WSL 镜像，并与微软发行版清单中的 SHA-256 比对一致。尚未注册或启动该发行版。

WSL 安装包的 Authenticode 状态为 `Valid`，签名者为 Microsoft Corporation，SHA-256 与 GitHub release asset digest 一致：

`28b1a0d013640a2ac95898ea705fa186e5b4ff767a1c1b49257161bc106599c6`

Ubuntu 镜像 SHA-256：

`bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e`

## 重启前的阻塞记录

Windows 的 `CBSRebootPending` 为 true，当前启动会话 `HypervisorPresent` 仍为 false。这是系统更改尚未经过重启的状态，不能据此宣布容器运行环境已全部就绪。

上述阻塞已在用户手动重启后解除。没有创建开机自动安装任务。

## 重启后验证结果

用户报告已重启后进行了只读复查，并保存了检查记录：

- Windows 本次启动时间为 2026-10-10 20:09:04（Asia/Hong_Kong），晚于此前记录的启动时间，确认已重启。
- `VirtualMachinePlatform` 为 `Enabled`。
- `HypervisorPresent` 已从 false 变为 true，虚拟化管理程序已实际运行。
- 启动配置 `hypervisorlaunchtype` 为 `Auto`。
- `CBSRebootPending` 已从 true 变为 false。
- WSL 版本查询和状态查询均返回 0；版本 3.0.1.0，默认 WSL 版本为 2。
- 检查时可用内存约 18.9 GiB。
- WSL 发行版列表报告尚未安装任何 Linux 发行版。因此本轮只确认 Windows / WSL 基础状态，尚未验证 Linux 启动或 Docker 容器运行。
- 证据文件：`logs/post-reboot-verification.json`。

## 后续步骤

重启后的执行顺序：

1. 重新检查虚拟机平台、`HypervisorPresent`、WSL 状态、内存和所需端口。
2. 使用已校验的镜像创建项目专用 `CRA-Ubuntu-24.04` 发行版，将虚拟磁盘放到 `runtime/wsl/CRA-Ubuntu-24.04/`，确认 WSL 2 能实际运行。
3. 按 Docker 官方 Ubuntu 安装指南安装 Docker Engine 和 Compose 插件，运行容器测试并检查服务状态。
4. 核对 CRA 套装与 Twenty 的版本要求，使用合适的稳定版本配置并启动 Twenty CRM，验证数据库、后台任务及本地网页访问。
5. CRM 正常后再进行 CRA Skill 安装和业务初始化。

以上部署步骤已继续执行。无需准备 VPS 或 SSH。

## 本地部署完成记录

- 专用发行版 `CRA-Ubuntu-24.04` 已导入到项目运行目录，Ubuntu 24.04.5 LTS、WSL 2、systemd 启动正常。
- Docker Engine 29.9.0 和 Compose 5.6.0 已从官方 Ubuntu 仓库安装，`hello-world` 实际容器测试通过。
- Twenty 官方稳定发布 `twenty/v2.45.0`，提交 `7e1431c84adbb264db98ab8b8d008a8401b6d4d6`。server / worker 同镜像；PostgreSQL 16、Redis 7.4；镜像摘要已锁定到 `deployment/twenty/compose.override.yaml` 和 `image-lock.json`。
- Docker Hub 初次直连超时。已使用原有 Windows 代理配置仅供当前 WSL 客户端访问的本地转接，未修改原有代理或 IPv6 设置。详细配置和系统设置位置见使用说明。
- 应用内部也已配置出网代理，Node 对 NPM 的读取测试返回 200。数据库和 Redis 等内部访问排除代理。
- 数据库初始化和迁移成功。数据库、Redis、网页健康检查通过；worker 正常运行，日志记录实际处理定时队列任务。
- Windows 访问 `http://localhost:3000/healthz` 返回 200 / `status: ok`；浏览器实际显示中文首次登录 / 注册页面。
- 已实际停止全部 CRM 服务、终止该项目 WSL 发行版，再通过 Windows 启动入口恢复服务。数据库表数重启前后均为 75，健康检查恢复正常。
- 首份备份 `backups/20261010T144737Z/` 已恢复到新建临时数据库，恢复前后表数均为 75，备份校验通过；该临时数据库随后清理。
- 已安装 CRA v0.3.5 套装的三个技能及所有随包资产，共 80 个文件，源文件与项目副本逐文件 SHA-256 比对通过。
- 已准备 Windows 启动、停止、备份入口和使用说明。未设置登录自动启动。

## 尚待使用者初始化的事项

- 账户信息由使用者自行填写。最终浏览器观察显示首次向导已进入“邀请您的团队”页；代理未读取或设置使用者密码。尚未验证客户 / 联系人 / 商机操作和实际附件上传。
- SMTP、邮箱 / 聊天渠道、模型 API、企业字段、规则与工作流尚未配置。
- 本轮完成的是本地 CRM 平台与 Skill 文件安装，不表示整套 CRA 业务自动化已上线。

## 文件位置

- 安装包及镜像：`.cache/installers/`。
- 检查证据、Windows 组件日志、WSL 安装日志及校验记录：`docs/deployment/logs/`。
- 计划中的 Linux 虚拟磁盘及容器运行数据：`runtime/wsl/CRA-Ubuntu-24.04/`。
- 后续业务记录：`records/`；备份：`backups/`。
- Windows 组件和 WSL 系统程序由系统安装器管理，位于系统目录；它们不是业务数据。

## 官方依据

- [Twenty Docker Compose 部署指南](https://github.com/twentyhq/twenty/blob/main/packages/twenty-docs/developers/self-host/capabilities/docker-compose.mdx)
- [Docker Desktop Windows 系统要求](https://docs.docker.com/desktop/setup/install/windows-install/)
- [Microsoft WSL 安装指南](https://learn.microsoft.com/en-us/windows/wsl/install)
- [Microsoft WSL 3.0.1 发布页](https://github.com/microsoft/WSL/releases/tag/3.0.1)
- [Microsoft WSL 发行版清单](https://github.com/microsoft/WSL/blob/master/distributions/DistributionInfo.json)
- [Docker Engine Ubuntu 安装指南](https://docs.docker.com/engine/install/ubuntu/)
