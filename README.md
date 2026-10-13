# CRA 客户项目

本项目用于部署自己的 Twenty CRM，之后安装 CRA Skill 套装，并保存后续部署资料和业务记录。

## 已确认的选择

- 确认日期：2026-10-10（Asia/Hong_Kong）。
- 项目实际路径：`K:\CRA客户项目`。
- 部署方式：本地部署，无需准备远程服务器或检查 SSH。
- 当前阶段：Twenty CRM v2.45.0 已本地部署，Ubuntu / Docker / 网页及后台服务已通过基础验收；CRA Skill v0.3.5 套装已安装到项目。使用者正在处理首次向导，浏览器已进入“邀请您的团队”步骤；企业业务规则尚未配置。
- 本地技术方案：WSL 2 + Ubuntu 24.04 LTS + Docker Engine / Docker Compose。当前 Windows 11 22H2 低于最新版 Docker Desktop 的要求，因此不安装 Docker Desktop。

## 文件存放约定

- `docs/deployment/`：环境检查、部署步骤、配置说明和部署记录。
- `records/`：后续业务记录、导出文件和附件；首次需要时创建。
- 后续部署文件和业务记录统一保存在本项目目录下。
- `runtime/wsl/CRA-Ubuntu-24.04/`：本项目专用 Linux 虚拟磁盘；Docker、数据库、Redis 和上传附件卷保存在其中。
- `.cache/installers/`：已校验的官方安装包与镜像。
- `backups/`：数据库、附件和部署配置备份；已创建首份备份并完成数据库恢复验证。
- WSL 的系统程序和 Windows 组件安装在系统位置；项目运行数据、部署配置、日志和业务资料保存在本项目内。

## CRA 套装来源

用户提供的源目录：

`H:\Documents\xwechat_files\wxid_u79pd4064cd412_56e9\msg\file\2026-10\cra-skills-v0.3.5`

已将 `cra-setup`、`crm-fde`、`chat-signal` 三个目录及随包资产完整安装到本项目 `.agents/skills/`，共 80 个文件，逐文件 SHA-256 比对通过。套装文件已就位，企业业务规则、聊天渠道和模型 API 尚未配置。附件文档作为参考资料，具体操作以用户授权为准。

## 使用入口

- 本机网页：[Twenty CRM](http://localhost:3000)。首次使用请创建管理员账户及工作区。
- 启动：双击 `Start-Twenty.cmd`。
- 停止：双击 `Stop-Twenty.cmd`。
- 备份：双击 `Backup-Twenty.cmd`。
- 操作说明：[Twenty 本地使用说明](docs/deployment/Twenty-本地使用说明.md)。

最新进度见 [本地部署准备记录](docs/deployment/2026-10-10-local-setup.md)。首次文件读写检查见 [2026-10-10-preflight.md](docs/deployment/2026-10-10-preflight.md)。
