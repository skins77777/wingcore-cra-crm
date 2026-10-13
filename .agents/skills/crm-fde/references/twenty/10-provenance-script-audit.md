# 经验来源、证据边界与旧脚本复用审计

整理日期：2026-09-20。以下是原“自动化 CRM”项目内的相对路径，**不是本 Skill 的运行依赖或链接**。本 Skill 已写出必要方法；客户不需要原仓库。维护者要追溯时才查原文件。

## 主要证据来源

| 原项目路径 | 用于提炼 | 证据边界 |
|---|---|---|
| `infra/p0/twenty.compose.yml`、`twenty.env.example` | 服务、版本、卷、端口、密钥与启动职责 | 已有实例升级配置，不是通用新装模板 |
| `docs/p0/local-twenty-migration-2026-09-20.md` | 备份、恢复、升级、字段/工作流迁移、白屏、离线恢复 | 主执行记录；后续小节会覆盖早期状态 |
| `docs/p0/status.md` | 早期本地探针、云端切换、工具接入状态 | 历史快照，不能覆盖后来的本地迁移 |
| `docs/p2b/crm-field-inventory.md` | 六类对象及字段结构 | 当时字段盘点，不是客户必装清单 |
| `docs/p3/cloud-schema-contract-2026-09-18.md` | 内部名、枚举、富文本、字段回读 | 云端字段契约，未证明所有工作流 |
| `packages/crm/src/twenty-schema.ts` | 评级、金额、富文本、姓名编码与白名单 | 代码实现；有公司及入口特有限制 |
| `docs/p3/money-extraction-repair-2026-09-20.md` | 金额单位、原币/统计币、修正回读 | 一次受控修正，固定汇率不可泛化 |
| `docs/p3/outbox-and-mapping.md` | 幂等、条件更新、外部实体映射与有限重试 | 项目外部执行层，不是原生工作流保证 |
| `docs/p3/cloud-write-pilot-2026-09-18.md` | 云端受控写入与版本验证 | 测试记录上的证据 |
| `docs/p3/approval-center-2026-09-20.md` | App 配置、变量、页面、身份与验收不足 | 云端与本地段落有演进，按时间读取 |
| `apps/twenty-approval/README.md`、`package.json` | App 架构、SDK/Node 基线、构建入口 | 源 App 没有包含在分发包 |
| `apps/twenty-approval/src/application-config.ts` | 六类 App 变量及 Secret 标记 | 实例配置已脱敏提炼，未复制值 |
| `apps/twenty-approval/src/logic-functions/run-crm-sync.logic-function.ts` | 手动入口与 UTC Cron 共用实现 | 配置/代码证据不等于真实 Cron 已触发 |
| `docs/p2/cron-recovery-2026-09-18.md` | 真实调度与模拟分离、分层排错 | 云端分析调度证据，不替代 Twenty Cron 验收 |

官方在线资料在对应章节直接链接：Docker Compose、升级、API、工作流版本、App 同步与恢复。仅把已读的官方说明作为当日参考；实施需重新核实目标版本。不复制在线手册全文，也不把源码中的内部接口当公开稳定契约。

## 旧脚本逐项归类

下表均位于原项目 `scripts/twenty-local/`。它是静态复用审计，不是建议客户执行的命令清单。即使名称带 `verify` 或默认有计划模式，也可能读取凭据、写本地文件或访问固定实例。

| 文件 | 实际用途/副作用 | 保留的方法与复用前工作 |
|---|---|---|
| `export-cloud-metadata.mjs` | 读远程配置、可能刷新 OAuth、写本地导出 | 保留分页/响应状态/清单；改为显式目标、保护输出、检查完整性 |
| `export-workflow-logic-functions.mjs` | 读函数及源码、写导出 | 保留递归查找函数依赖；检查源码是否含敏感值 |
| `audit-cloud-local-metadata.mjs` | 读取两套导出并比较 | 保留按内部名规范化比较；版本差异需分类，不要求全量零差异 |
| `prepare-upgrade-env.mjs` | 读取旧敏感配置并写新环境文件 | 仅适用于旧密钥回退历史；不是通用 dotenv 解析器/密钥轮换器 |
| `configure-local-api-key.mjs` | 可能生成 Key、写钥匙串、配置 CLI remote | 改用客户支持的认证流程，不照搬固定容器/开发环境覆盖参数 |
| `replicate-cloud-custom-fields.mjs` | 计划；`--apply` 时创建/更新字段 | 保留语义差异与回读；移除固定日期、目录、实例和字段假设 |
| `reconcile-local-metadata-contract.mjs` | 计划；`--apply` 时改字段/对象/分组 | 保留枚举与看板分开对齐；不要保留“唯一七组看板”定位假设 |
| `import-cloud-workflows.mjs` | 导入、内部认证、核心及工作区表写入、激活 | 仅保留依赖映射/比较方法；执行部分需用支持入口重写 |
| `prepare-system-workflow-replacements.mjs` | 计划/复制内置流程，内部认证与本地记录写入 | 保留平台复制函数依赖的思路；改为正规认证和目标能力检测 |
| `delete-old-workflows-and-activate-replacements.mjs` | 按旧固定清单逐个软删除/激活 | 一次性迁移修复，**不分发为通用清理脚本** |
| `protect-person-company-workflow.mjs` | 修改版本/条件、直接内部表写入、激活 | 保留关系为空保护；不能整组覆盖现有过滤条件 |
| `register-local-approval-app.mjs` | 注册 App 的元数据变更 | 注册成功不等于同步与功能验收；换用目标支持入口 |
| `configure-local-approval-app.mjs` | 写目标 App 变量/Secret | 参数化工作区、成员、地址与凭据来源；禁止输出值 |
| `inspect-neon-local-migration.mjs` | 读取外部数据库状态 | 仅扩展需要；目标数据库身份先核对 |
| `provision-neon-local-workspace.mjs` | 计划；`--apply` 写逻辑工作区与设置 | 保留配置/业务实体分离；不能复制旧映射/旧队列 |
| `install-local-crm-writer-launchd.mjs` | 写主机 plist、注册定时任务 | **已被 Twenty App Cron 替代的历史方案**，不随基础安装启用 |
| `run-local-crm-writer.mjs` | `--enable` 后运行受限 Writer | 基建不需要；未来参数化目标和批次，保留关闭默认与执行证据 |
| `seed-local-crm-acceptance.ts` | 创建测试业务数据/任务 | 是写入测试，不是只读检查；需隔离且标识唯一 |
| `test-local-crm-writer-chain.mjs` | 构造/执行受控写入并核验 | 保留离线/重试证据设计；不能对真实客户套固定 ID |
| `test-person-company-guard.mjs` | 构造联系人关联测试、调用 Writer | 保留关联不被覆盖的负向测试；另补无关联正向用例 |
| `verify-local-crm-acceptance.mjs` | 读 Twenty 和外部 DB，核对固定测试记录 | 改为客户自己的断言，不把历史数量当基准 |
| `verify-review-api.mjs` | 未授权/授权列表读取 | 读取真实配置与凭据；只能验证所覆盖接口 |
| `verify-review-api-decisions.mjs` | 创建/通过/拒绝/重放测试请求 | **会改变状态**，不能当作只读 verify；仅扩展隔离环境使用 |

## 将来真的做安装器时还缺什么

当前交付是知识与实施方法，没有把旧脚本拼成所谓一键安装器。若另行产品化执行器，应完成：

1. 显式输入目标 URL、工作区、版本、运行方式与凭据引用；拒绝隐式回退到作者账号。
2. 只读能力检测与差异计划；计划描述影响对象、需要的前置条件及恢复点。
3. 使用受支持接口，逐项幂等应用并回读；错误到具体资源，不靠反复全量重建。
4. 所有写入测试有隔离目标、数据标识和范围，正常运行不删除客户资源。
5. 敏感日志脱敏，输出证据摘要；重试有边界，冲突不静默覆盖。
6. 新装、接管、升级、迁移分别验收；不同版本的支持矩阵来自实际测试。

优先值得工具化的是语义盘点、字段/枚举差异、引用映射完整性和结果回读。内部数据库修复与旧资源删除不适合作为自动安装的第一批能力。
