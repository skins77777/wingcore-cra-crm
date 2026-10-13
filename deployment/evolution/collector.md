# WhatsApp 本地持续采集

2026-10-12：使用当前已授权的 wingcore-business 实例与已核实账号 +86 153 6161 5301，通过本地 Evolution 官方只读查询接口采集。接口来源：https://raw.githubusercontent.com/EvolutionAPI/evolution-api/2.3.7/src/api/controllers/chat.controller.ts 。分页返回契约通过本地 2.3.7 实测核对。

`scripts/collect-whatsapp.py` 每次重新核对实例号码、读取连接状态，并分页核对服务现有消息。当前只有40条，采用全量对账可以发现同消息内容变更，而不是只按发送时间跳过旧消息。分页上限100页；总数变化、重复页或缺页停止本次提交，保留原证据，下次任务重试。成功采集的消息与本次运行信息以同一 SQLite 事务保存。

证据保存到 ACL 保护、已被 Git 忽略的 `records/chat-signal/whatsapp.sqlite3`。消息按实例、会话、方向、外部消息ID去重；内容摘要作为版本，变更保留旧版，当前指针只指向本次观察到的版本。发生时间缺失保持未知。群聊与状态广播排除。

本脚本不发送消息、不调用已读接口、不下载媒体、不调用模型、不写CRM。媒体说明文字可读时保存；媒体内容明确记为未下载。协议消息保留为修订事件待核对，不能宣称撤回/编辑事件联动已经完成。API返回缺失的消息不推断删除，也不宣称手机历史已完整回补。连接状态单独记录，断线不会因已有历史仍可读取而被隐藏。

Windows任务 `CRA-Wingcore-WhatsApp-Collector` 每分钟及当前用户登录时执行，不允许并发，10分钟超时。运行前提是电脑开启、用户登录、WSL/Docker和Evolution正常。失败只写脱敏错误类型和时间；原数据库保留，不记录密钥。

手动只读检查：

```powershell
& 'C:\Program Files\Python312\python.exe' scripts/collect-whatsapp.py
Get-ScheduledTaskInfo -TaskName 'CRA-Wingcore-WhatsApp-Collector'
Get-Content records/chat-signal/whatsapp-status.json
```

停用持续采集：

```powershell
Disable-ScheduledTask -TaskName 'CRA-Wingcore-WhatsApp-Collector'
```

后续分析只能使用当前有效版本，并继续补齐协议事件解析、修订依赖失效、断线缺口和媒体来源关联。当前采集定时器不是模型实时分析或CRM自动更新的上线证明。
