# 经验来源与有效边界

本版从维护者的 CRM 原型源码与 2026-09-18 至 2026-09-20 的验收记录，以及 `crm-fde` 基建交付方法提炼。这里的路径仅供维护者追溯，不是运行依赖；技能已写出可复用方法，不要求客户访问原仓库。

| 来源类别与相对路径 | 提炼内容 | 不能据此宣称 |
| --- | --- | --- |
| `packages/connectors/src/evolution.ts`、`apps/edge/src/index.ts` | payload 标准化、工作区/实例核对 | 多号、所有媒体和所有供应商事件都支持 |
| `infra/p1`、`apps/edge/src/database.ts` | 事务、事件/消息去重、证据 | connected 意味着历史补齐 |
| `packages/ai/src/event-context.ts`、`event-extraction.ts` | 路由、按商机选上下文、金额与小结 | 真实业务准确率已经充分验证 |
| `packages/domain/src/company-rules.ts`、`business-events.ts` | 业务规则与事件投影 | 支持任意行业阶段与条件 |
| `packages/crm/src/twenty-schema.ts` | 金额/枚举/富文本编码、门禁 | 旧字段和枚举适用所有客户 |
| `packages/crm/src/dispatcher.ts`、`packages/persistence/src/crm-outbox-postgres.ts` | 租约、generation、幂等、远端版本回读 | 跨系统 exactly-once 或任意接口原子更新 |
| `apps/twenty-approval`、`apps/edge/src/p3-review-api.ts` | 审核页面、服务端身份、决定与执行区别 | 新审核决定已完整接上执行 |
| `docs/p2/cron-recovery-2026-09-18.md` | 真实 Cron/Queue/模型/游标的分层证据 | 每个新客户 Cron 已经通过 |
| `docs/p2b/context-selection.md`、`known-issues.md` | 增量记忆、语义问题与验证层次 | 历史问题仅因换阶段就已修好 |
| `docs/p3/money-extraction-repair-2026-09-20.md` | 原币/统计币、退款区别、受控写入 | 已开放所有候选自动入队 |
| `docs/p0/local-twenty-migration-2026-09-20.md` | 本地/云端差异、执行器迁移与离线恢复 | 每个环境都需要电脑执行器 |
| `crm-fde` 的蓝图/字段/实施/变更教材 | 稳定 ID、唯一更新者、实际映射和版本 | 基建已自带聊天采集、AI 或成员权限 |

## 历史原型的显式局限

- 早期 Cloudflare Workers/Queues/Cron 与 Neon 的分工不是当前 VPS 版部署方案。2026-09-25 VPS 迁移记录将业务后台集中到 VPS，Cloudflare 仅保留 HTTPS 入口与私有连接。当前客户版只分 VPS/本地，按 [部署指导](02-deployment.md) 实施；本地既有依赖单独核实，不将历史云端能力当作关机后仍可运行的保证。
- 存在绑定单账号、测试工作区、固定资源 ID 和内部地址的部署配置。
- 部分行业阶段、单位和赢单组合仍写在代码，不能只换提示词或 JSON 就支持所有客户。
- 早期记录保留候选模式和自动入队关闭；后续 VPS 的部分自动写入及审核后执行已接通，按具体版本核对，不能用早期状态推断当前能力。
- 附件元数据与附件下载/识别不同；能力随分支与部署版本核对。
- 原部署、迁移和补写脚本可能携带固定目标、内部认证或直接写核心表；本包没有复制这些一次性脚本。

不能把这一页当作新客户的待办全集。按实际选择的能力复核，保留用户已确认规则和既有授权，完成所需改造。

## 版本与资料更新

软件 API、模型能力、套餐和许可会变化。实施相关服务时查询该版本官方文档，并在客户记录中保存资料时间与实际回读证据。技能自身版本更新是知识更新，不代表客户后台、数据库或规则已升级。

维护者可在项目级 `docs/source-manifest.json` 查看本次所读源文件摘要。该清单不包含源数据或密钥，也不随最小 Skill 包作为运行依赖。

## 本次补充的参考经验与适用边界

进一步参考维护者截至 2026-09-27 的本地实现：`packages/ai/src/event-context.ts`、`event-extraction.ts` 的归属/提取/小结三步；`packages/domain/src/chanyi-rules.ts`、`business-events.ts` 的字段语义和阶段条件；`packages/connectors/src/imap-email.ts`、`apps/vps/src/email-sync.ts` 的邮件读取；`apps/vps/src/import-identities.ts`、`planner.ts` 的身份和字段更新。

提炼的是方法，不复制实际客户记录、固定字段 ID、行业阈值、汇率或凭据。参考代码仍含固定阶段验证和条件组合，不能直接称为通用企业规则执行器。其 WhatsApp/Email 共用处理链也不证明跨渠道统一分析和小结已经完整实现；客户现场需要分别核实。

本次依据本地代码和已有记录学习，没有重新验证生产模型效果或线上服务状态。规则、源文件与历史部署时间不同，优先核对实际版本，不把旧状态说明作为当前故障结论。

## CRA 套装修订

按项目所有者要求，CRA v0.3.0 随包提供 [客户版待审核应用](../assets/twenty-approval/README.md)。布局与导航沿用原 App 结构，页面内容、后台接口和身份配置按客户化要求整理，使用新应用标识；保留私有分发属性。规则类型、业务对象、证据和展示字段从客户后台提供，不携带作者实例或固定三类审核限制。应用源码和合成测试可离开作者仓库构建，后台持久审核与执行需在客户环境接通。

CRA 套装与独立 chat-signal 项目共同维护本技能；内容是否一致须比较实际文件，历史同步记录不代表后续修改也已同步。支持独立使用，不要求其他 Skill 文件存在。历史验证与静态包检查不代表在新客户环境完成部署；以该客户实际验收为准。来源与同步摘要由制作项目维护，不要求客户取得作者源码。
