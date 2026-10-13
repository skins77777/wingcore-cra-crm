# 已有客户与商机摘要更新

2026-10-12部署第一版受限摘要更新执行器。复用现有person/opportunity专用密钥，不扩大角色权限。仅允许craChatSummary文本字段；阶段、金额、订单、归属、姓名、公司、删除与主动消息均不在本执行器允许范围。完整自动字段更新仍须后续接通。

官方API支持依据工作区实际schema读写（https://docs.twenty.com/developers/extend/api）。现场Twenty 2.45.0源码核查：REST更新多条handler调用CommonUpdateManyQueryRunnerService，再经runFilteredMutation、WorkspaceMutationQueryBuilder生成单条UPDATE WHERE RETURNING，版本过滤直接参与写入。不是先按过滤查询ID再无条件PATCH。

实际采用PATCH /rest/people或opportunities加and(id[eq]:固定UUID,updatedAt[eq]:官方回读时间戳)，最多命中一个目标。先验证旧字段值和关系，再执行版本过滤；来源、身份绑定、规则、经营者背景、批准及租约代次亦须一致。匹配新版本GET实测返回1条；不匹配旧版本PATCH实测零更新，前后完整客户记录相同。首次真正匹配的更新与回读仍待审核通过后验收，不能把零命中探测当作已完成业务更新。

精确计划存于records/chat-signal/context-update-plan.json，绑定摘要、前后值、规则、证据、客户及远端版本。在Twenty原生待审核页提供“更新客户总览摘要”选择；批准与crm_update_outbox在同一SQLite事务保存；拒绝不入队，重复批准不重复入队。程序不能通过请求正文伪造批准。

Windows任务CRA-Wingcore-CRM-Update-Executor已配置登录及每分钟执行；实际触发02:35:35香港时间LastTaskResult=0，当时未批准项、更新队列0，没有业务写入。租约5分钟、递增代次、总尝试最多3次，429/5xx与网络错误有界退避，权限/计划/版本冲突终止。超时先回读，已是目标值视为满足而不重复写；只在官方回读核对后持久保存成功证据。摘要当前快照同时刷新以供后续候选分析。失败/冲突出现在独立系统处理异常区，不作为业务批准事项。

8项更新执行测试及15项审核后台测试通过，包含人工改动、读取与写入间竞争、超时已提交恢复、重复执行、篡改计划、越权字段、批准重复、拒绝不入队和来源失效回滚批准。真实系统异常区当前0。证据records/chat-signal/context-update-verification.json；待审核截图context-update-review.png。模型调用0、真实业务字段更新0。自动模型调度、R02-R11阶段/报价/履约事实映射及订单联动尚未启用。

第一份计划整理乌兹别克斯坦客户总览：阿里来源、未知姓名/公司/具体收货地点、样品暂缓与七个PCBA项目等待消息。沿用现有两条独立商机，不改变订单、付款或成交。经营者审核后应再次核对该客户摘要、两条商机关系和执行结果。
