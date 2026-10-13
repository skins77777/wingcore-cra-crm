# 本地重启恢复与终端闪窗修复

## 原因

重启后 CRA-Ubuntu-24.04 没有持久的 Windows 侧 WSL 保活进程。短命 WSL 命令只能临时启动发行版，不能作为持续运行的保障。Twenty 和 Evolution 的容器重启策略存在，但此前没有登录时恢复 WSL 的计划任务。

CRA-Wingcore-Review-Backend 每分钟通过 powershell.exe 启动。启动参数中的隐藏窗口不能保证控制台宿主创建时完全不闪窗。

## 修复

- 审核后台计划任务改为直接执行 Python312/pythonw.exe 与 scripts/start-review-backend.py。内部 PowerShell 使用 CREATE_NO_WINDOW；继续复用原脚本的端口归属核验。
- 新增 CRA-Wingcore-Local-Services：当前用户登录后运行，并每分钟检查；IgnoreNew 防止重叠，最长运行五分钟。
- scripts/start-local-services.py 核实项目 WSL 保活进程；失效时创建无控制台的 sleep infinity 进程，写入 runtime/wsl-session.json。
- 核实 Twenty/Evolution 两套既有 Compose 服务。健康时不重启；未运行或不健康时使用 up -d --pull never --no-build --wait 恢复，不安装软件、不拉取镜像、不删除卷。
- 在现有地址及现有防火墙范围内，恢复无控制台的项目代理。子进程身份查询明确使用 UTF-8，避免中文项目路径被 OEM 编码破坏。

## 实测

2026-10-12 香港时间约 03:46：

- 新计划任务手动触发和后续分钟定时触发均返回 0。
- 将保活状态暂置为失效 PID，验证计划任务创建新保活进程；核实新进程后停止旧的项目保活进程。WSL 和容器持续运行超过一分钟，没有反复启动容器。
- 七个项目容器持续运行；具备健康检查的数据库、Redis、Twenty server 均健康。
- Twenty /healthz、订单报表 /api/report、审核 /v1/review/errors 均返回 HTTP 200；报表实际读取十条订单，无查询错误；审核系统异常数为 0。
- WhatsApp connectionState 为 open，采集正常；邮箱及 R02 状态更新正常。
- 七项恢复回归测试通过：PID 复用、保活复用、健康服务不重启、禁止拉取/构建、地址变更拒绝误用、无控制台子进程、中文路径编码。
- 原计划任务中持续运行的订单报表返回 267009，表示运行中，不能当作失败。

机器可读证据：runtime/reboot-recovery-verification.json。尚未再次重启整台电脑；登录触发配置已注册，本次验证的是任务执行、真实分钟触发、保活恢复和持续运行。

## 维护边界

本地服务依赖电脑开机且用户登录；关机、休眠或退出该用户会中断采集。

当前 WSL 网关为 172.22.176.1，客户端为 172.22.191.211。现有代理防火墙仅允许这一 WSL 客户端。若未来 WSL NAT 地址改变，恢复器不会扩大防火墙或猜测复用旧代理，会在 runtime/local-services-status.json 标记 wsl_addresses_changed_run_Start_ImageProxy。此时须由 Codex 核实当前地址，使用已有 scripts/Start-ImageProxy.ps1 更新受限防火墙及项目代理，并同步核实审核后台 WSL 绑定和 Twenty 应用访问地址。

Windows 上游代理 127.0.0.1:10808 由现有代理软件提供。恢复器不启动未知代理软件；上游状态单独记录为 upstreamAvailable。

本次未改业务规则、审批决定、模型重试次数或客户订单；报价图片接入仍停留在此前调查阶段。
