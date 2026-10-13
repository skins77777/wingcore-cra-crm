# 付款后采购与物流准备提醒：实施记录

更新：2026-10-11。用户已明确授权创建及安全保存受限后台凭据；字段、正式代码、真实后台完成事件和业务规则验收已通过。两个工作流已启用，首次真实定时扫描已通过。下述最新状态取代早期“后台凭据待授权、未启用”记录。

## 已部署

| 流程 | 工作流 ID | 当前发布版本 | Logic Function ID | 状态 |
|---|---|---|---|---|
| T2｜付款后采购与物流准备检查 | 8aea8338-d263-468c-a171-4b09d7c0c204 | 998ec106-9249-4b6e-9c0a-a52f22c399a2 | 554f7d16-5453-4a91-8746-b0e87074b6c1 | ACTIVE；每五分钟扫描 |
| T2｜记录实际检查完成时间 | 62b194cc-e26c-4065-bcb7-9b69dacc90a1 | 9adbe950-b4f2-409d-8328-4a98668ab521 | 9f0049c9-8ed2-41e7-b4f5-f2ef3a85472d | ACTIVE；task.updated，限定 status |

参数 taskId 和 completedAt 分别来自 trigger.properties.after.id 与 after.updatedAt。正式源代码为 t2-reminder.ts、t2-completion.ts；不含密钥、测试注入或清理逻辑。实际版本、触发器与步骤见 t2-workflow-mapping.json。

订单字段包括全款到账时间，两条准备线的完成勾选、约定检查时间及最近检查时间。任务字段包括唯一提醒去重键、实际检查完成时间、跟进订单关系及提醒失效原因。实际映射见 t2-metadata-mapping.json。

两项完成勾选默认值为 false。十笔历史订单新建字段时曾被默认 true 误填，已修正并逐笔回读 false；该修正不是经营者对历史准备状态的确认，不倒退实际履约阶段。

## 权限与安全保存

专用 key：CRA T2 本地后台提醒，ID 5f008ca5-60b8-437e-8914-ac9290f02078；绑定角色 T2后台提醒专用，c2beb0c2-e282-412b-85a7-4278cded9ffc。人员只读，订单/任务读写，无删除、销毁、系统管理或邮件权限。技术权限覆盖这些对象全部字段和记录；正式代码对订单仅写最近检查时间，不自动改变付款、报价、履约或准备完成。

选择 90 天有效期，实际到期香港 2027-01-09 15:50:41.553。应用变量 CRA_T2_API_KEY 在 Custom 应用中 isSecret=true，官方加密保存；只读验证 enc:v2 格式。项目私密副本受 Windows ACL 限制，gitignore 覆盖。非秘密恢复说明见 deployment/twenty/T2-credential-recovery.md。没有新增到期提醒自动化。

变量新增通过官方 SDK syncApplication：先 dryRun=true 且 inferDeletionFromMissingEntities=false，差异只有一项 create applicationVariable，再执行同步。Custom 的 defaultRoleId 保持 null，没有扩大应用默认权限。没有直接数据库写入、构造 JWT 或从隐藏浏览器状态提取认证。

此前后台 NO_AUTHENTICATION_CONTEXT 原因是 Custom 未赋后台权限；用户身份手动运行可成功但不能证明后台可用。正式代码现显式使用受限 key，缺变量时报错，不退回用户身份。

## 实际验收

- 18 项纯规则测试通过，涵盖香港日期边界、未核实/不足额付款、缺日期、约定优先、任务去重、分别停止等。
- 新独立测试订单 TEST-T2-20261011-03（943edb71-e1bc-4c49-809d-95c8865026bc）在受限 key 下创建两条任务；重复扫描保留两条；改约定时间更新原任务。三项通过，见 t2-key-stage1-result.json。
- 原生 status 完成事件运行 75e00ac0-0715-4d97-940d-d8db23cac6c3 COMPLETED：原事件 after.updatedAt 和写入完成时间均为 2026-10-11T11:26:41.424Z。不是手动注入或执行时刻代替事件时刻。
- 受限 key 下第二阶段七项通过：真实完成时间、完成后等两天、同步最近检查时间、模拟时间已过创建下一轮、采购独立停止、物流仍保留、安全收货停止。为测试时间跨度，在测试订单中将已完成任务时间改为三天前；未改真实订单。见 t2-key-stage2-result.json。
- 两项因准备完成/离开阶段而失效的 status 事件运行 9e68487a-6810-481d-afcd-3f88e360476f、2f754a7c-6de8-459c-a927-c9e4ad5f13fa 均 COMPLETED，结果 ignored=obsolete reminder, not an actual check；两项检查完成时间保持空。
- 测试事件完成后，通过当前操作用户的官方 SDK 单独执行 soft_delete=true，将该测试订单和三项任务放入可恢复回收站；后台 key 仍没有删除权限。见 t2-key-cleanup-result.json。前两次历史测试记录也留在回收站，无有效 TEST 订单或任务。
- 恢复正式代码后，在受限 key 下扫描真实十笔订单：scanned=10、created=0、kept=1、stopped=0、blocked=[]。见 t2-key-production-manual-scan.json。
- 首次真实 CRON 运行 e46440e2-da6f-4ade-81a1-85b9ee1ac9c9，于香港 2026-10-11 19:35:02 自动触发，COMPLETED；scanned=10、created=0、kept=1、stopped=0、blocked=[]。对应正式发布版本 998ec106-9249-4b6e-9c0a-a52f22c399a2，见 t2-cron-verification.json。不是手动测试触发。
- 只读核验：仍十笔有效订单，原金额合计 USD10938.53，两项有效业务任务；基准金额和实收未被测试改动。角色绑定、加密标志与后台事件证据见 t2-background-verification.json。

## 经营规则与当前实际任务

准备完成由经营者分别勾选，任务 DONE 只代表完成本次检查。失效任务写原因，不制造完成时间。未完成保留原任务；明确约定日期优先，无约定时按香港到账日/实际完成本次检查日加两天、23:59。未知到账时间且没有约定时间时不制造逾期。

Meruzhan 沿用原物流任务 85921b66-cea9-4b2f-91f6-4d598d28f807，已关联原订单及 T2 初始唯一键，约定时间保留香港 2026-10-12 23:59；任务内容、状态、负责人不改。Ruslan 原一次性任务保留，实收未核实，不自动进入 T2。Mehis 在目的国清关，Diana 已安全收货，不重开准备任务。Zoe 未付款，不启动采购。

任务 genJinDingDanId 关联订单，不依赖隐藏 taskTarget 权限。立即回读再写、唯一键和稳定 UUID 保护重复创建；不宣称实现多人并发的事务锁/CAS。当前只在本地 CRM 展示任务，不对外发送消息；电脑和本地后台关闭时不能按时扫描。

备份：配置前 backups/20261010T191606Z。后续继续每日汇率及统计；T1 报价、L1/L2 输单复核、其他运输提醒和聊天接入仍待实施。


## 本地时钟修复

首次与第二次真实 CRON 执行结果成功，但运行结束时间比开始时间早约16秒，不能用这两次历史记录计算耗时。只读检查发现 Windows Time 服务停止、Manual启动；WSL与宿主曾相差约16秒。

启动现有Windows W32Time服务，使用已有time.windows.com配置请求同步；首次请求无数据，随后服务获得同步。没有修改NTP服务器、时区或应用历史日期。Windows与WSL回读已相差不足一秒，WSL现有ntp.ubuntu.com参考偏差约-2.5ms。W32Time设置Automatic以在下次开机保持服务。

校准后重启Twenty server/worker以刷新长期运行进程的时间基准。历史运行时间不回填，后续另存真实运行开始/结束时间证据。该变更不修改任何业务订单日期或任务完成事实。

校准后的最终真实 CRON 运行：07d4200a-1b47-461f-a7c2-a5dcfe9e83e9，香港2026-10-11 19:45:00自动触发；COMPLETED，开始19:45:00.285、结束19:45:00.864，时间顺序正常。scanned=10、kept=1、created=0、stopped=0、blocked=[]；同一正式发布版本。证据：t2-cron-post-clock-verification.json。后台健康检查200，主机和WSL时间回读相差不足一秒；最终数据验证见t2-final-data-verification.json。
