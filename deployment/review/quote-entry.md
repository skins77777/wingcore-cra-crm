# 项目4：报价事实登记入口与后台安全边界

更新日期：2026-10-13，Asia/Hong_Kong。沿用项目4-B方案，结合 Twenty v2.45.0 隔离权限实验更新生产接入边界。

## 实施状态

报价前端、登录态服务端代理、本地路由、独立持久存储、条件更新、回读、恢复及本地测试已完成；独立 Twenty v2.45.0 实例已验证真实报价字段更新、禁止字段更新、业务对象隔离和删除拒绝。当前未配置或启用生产报价凭据，未发布新应用函数，未重启现有审核服务，未写入真实商机。因此这是源码及隔离验证完成，不代表生产报价入口已上线。

商机侧栏入口与命令源码已存在，尚未发布。本模块不包含图片上传、AI/图片识别、WhatsApp/邮件读取或Twenty报价历史对象。运行记录仅用于最新登记、最近验证的已发送事实和幂等恢复，不提供报价历史列表或版本比较。

## 生产接入安全边界

- `CRA_QUOTE_API_KEY` 仅存在客户 Python 后台的受保护配置中。不得加入 Twenty 应用变量、前端环境变量、构建产物、接口响应或日志。
- `CRA_QUOTE_API_TOKEN` 是 Twenty 服务端函数与 Python 后台的独立通信凭据，只存在这两端；应用变量标记为 Secret。浏览器不得取得或使用它。
- 前端仅通过登录态 SDK 调用 `/s/cra-quotes/read` 和 `/s/cra-quotes/register`。不直接读取或修改 Twenty `/rest` 对象接口，不直接访问 Python 后台。
- 服务端函数从认证上下文 `context.workspaceMemberId` 获取登记人；请求体不能指定 actor、成员、工作区、任意 URL、GraphQL 查询或字段选择。函数和后台均校验成员与商机范围。
- Python 后台的远端读取适配器固定仅保留 `id`、`updatedAt`、`deletedAt`、`craT1QuoteRound`、`craT1QuoteSentAt`、`craT1QuoteEvidence` 六个字段。必要字段缺失则报错；上游附带的 `name` 或其他字段不会透传。
- CRM 写入固定仅有三个报价字段；前端提交的是报价事实和提交/版本信息，不是可自由选择字段的 CRM PATCH。Twenty 自动维护所需 `updatedBy`，不允许调用方提交它。
- 后台拒绝 Twenty HTTP 重定向，避免 Authorization 跟随跳转到其他地址。没有提供通用 REST/GraphQL 代理或删除接口。
- 网络仅允许可信服务端访问后台，后台配置文件及持久目录仅允许必要系统账户访问。通信 Token 持有者属于信任边界内，能够代表配置中的授权成员，不能把网络认证视为独立最终用户身份。

Twenty v2.45.0 会强制允许读取 Opportunity 的名称标识字段 `name`。这属于上游 Key 的已知能力；本方案通过后台响应白名单隔离前端，不能宣称 Key 本身无法读取名称。独立权限实验还证明更新报价字段需要 `updatedBy` 更新授权，但它可以继续拒绝读取。接受该服务端边界后，不继续修改 Twenty 权限模型。

## 文件

新增：

- `scripts/quote_entry.py`：独立业务模块、Twenty客户端、HTTP分派、SQLite在线备份。
- `scripts/test-quote-entry.py`：业务、权限、崩溃恢复、并发、路由和API契约测试。
- `integrations/twenty-approval/src/lib/quote-entry.ts`：服务端身份与后台通信契约。
- `integrations/twenty-approval/src/logic-functions/get-quote-entry.logic-function.ts`：登录态读取代理。
- `integrations/twenty-approval/src/logic-functions/submit-quote-entry.logic-function.ts`：登录态登记代理。
- `integrations/twenty-approval/src/front-components/quote-entry.tsx`：只调用报价后端函数的侧栏表单。
- `integrations/twenty-approval/src/command-menu-items/quote-entry.command-menu-item.ts`：侧栏入口声明。
- `integrations/twenty-approval/tests/quote-entry.test.ts`：代理权限和通信测试。
- `deployment/review/quote-entry.env.example`：默认关闭的后台配置示例。
- `deployment/review/quote-entry.md`：本说明。

修改：

- `scripts/review_backend.py`：报价路径在审核认证、数据库打开和候选刷新之前分派，报价模块自行认证。
- `integrations/twenty-approval/src/application-config.ts`：报价通信Token、工作区和成员范围三个服务端配置变量。
- `scripts/backup-twenty.sh`：有报价存储时添加SQLite在线备份及校验和。

首次使用时创建：`records/quote-entry/registration.sqlite3` 和 `.lock.sqlite3`。测试全部使用临时路径，不生成生产登记记录。

## 数据流程

1. Twenty认证HTTP函数从`context.workspaceMemberId`取得当前成员，拒绝请求体提供登记人、工作区或登记时间。
2. 服务端按成员的明确商机范围检查权限，再用报价专用Token向本地后台发送请求。通信Token和Twenty写入Key均不传给浏览器。
3. 后台独立核对Token、工作区和同一成员授权范围；校验请求状态、UUID、字段、时间与必填内容，通过专用Twenty Key确认商机存在且未删除，并将远端记录裁剪为固定六字段。
4. 按提交编号保存不可变请求、登记人、服务器时间、处理状态、尝试次数、结果和错误码。
5. `unknown`、`not_quoted`、`draft`只保存登记，不修改任何CRM字段。
6. `sent`持久保存写入前商机版本和目标三个字段；使用`id + updatedAt`过滤条件发出一次PATCH，同时更新三个字段。
7. 重新GET商机，逐项比对三个字段；时间比较按实际UTC时刻。只有回读一致才保存`succeeded`及验证结果，更新最近验证的已发送登记指针。
8. 现有T1在原有扫描中自行读取报价字段，不由本模块创建任务。

SQLite中的`submissions`是幂等运行记录；`latest`只保存最新登记及最近验证的已发送登记指针。处理失败的提交仍可按编号查询。保存登记并不等于CRM更新成功。

## API

### Twenty登录态服务端函数

应用发布并配置后才可访问：

| 路由声明 | 方法 | 请求体 |
|---|---|---|
| `/cra-quotes/register` | POST | 报价登记请求 |
| `/cra-quotes/read` | POST | `opportunityId`，可选`submissionId` |

两者均设`isAuthRequired: true`；使用Twenty函数的实际调用URL。读取使用POST以沿用当前SDK的认证函数调用方式，本地读取仍为GET。

### 本地后台接口

| 接口 | 作用 |
|---|---|
| `POST /v1/quotes/registrations` | 提交或安全重试原登记 |
| `GET /v1/quotes/opportunities/{opportunityId}` | 读取当前T1字段、商机版本、最新登记及最近验证已发送登记 |
| 同上，附`?submissionId={uuid}` | 查询指定提交的处理结果 |

必须提供：

- `Authorization: Bearer <CRA_QUOTE_API_TOKEN>`
- `x-cra-workspace-id: <CRA_QUOTE_WORKSPACE_ID>`
- `x-cra-member-id: <来自Twenty登录上下文的成员UUID>`

本地接口为可信服务端之间的接口。持有通信Token的服务端可代表授权成员；不得将它当成直接给浏览器使用的用户Token。本地后台只使用管理员明确配置的报价登记授权范围，不自动继承Twenty全部角色或负责人权限。专用Twenty Key的实际权限再由Twenty强制检查。

六字段限制应用于后台读取 Twenty 记录的适配器；报价 HTTP 接口的响应是登记业务结构，包含 `opportunityId`、`expectedUpdatedAt`、三个字段组成的 `t1Fields`、最新登记和处理结果，并非直接返回一份六键 Opportunity。`deletedAt` 用于后台拒绝已删除目标，不向前端返回原始商机对象。名称、金额、阶段、公司和联系人均不进入该响应。

已发送请求示例（示例UUID不是业务目标）：

```json
{
  "submissionId": "4304bb0d-dd18-47eb-b3f0-e5d76281af01",
  "opportunityId": "c6c75dc6-9f6f-4e27-a27c-096c373217af",
  "status": "sent",
  "expectedUpdatedAt": "2026-10-13T01:00:00.000Z",
  "quoteRound": "Q-20261013-01",
  "sentAt": "2026-10-13T09:30:00+08:00",
  "channel": "alibaba",
  "evidence": "人工核实：本商机商品报价已发给客户，消息编号MSG-001"
}
```

状态固定为`unknown`、`not_quoted`、`draft`、`sent`。前三种只接受`submissionId`、`opportunityId`、`status`三个字段；携带已发送字段会被拒绝。

`sent`必须有`quoteRound`（最多120字符）、带时区且不在未来的`sentAt`（最多毫秒精度）、`channel`、`evidence`（最多4000字符），以及读取商机取得的`expectedUpdatedAt`。发送渠道为`whatsapp`、`email`、`alibaba`、`other`；`other`必须补充`channelDetail`。存储UTC时间；不把登记时间当作发送时间。

写入字段严格限定为：

```json
{
  "craT1QuoteRound": "Q-20261013-01",
  "craT1QuoteSentAt": "2026-10-13T01:30:00.000Z",
  "craT1QuoteEvidence": "阿里平台｜人工核实：本商机商品报价已发给客户，消息编号MSG-001"
}
```

调用形式：`PATCH /rest/opportunities?filter=and(id[eq]:{id},updatedAt[eq]:{expectedUpdatedAt})`，实际URL编码过滤表达式。回读为`GET /rest/opportunities/{id}`。响应的单记录形状为`data.opportunity`，条件更新为`data.updateOpportunities`，沿用项目现有字段更新执行器的协议。

提交响应：

```json
{
  "value": {
    "submissionId": "4304bb0d-dd18-47eb-b3f0-e5d76281af01",
    "opportunityId": "c6c75dc6-9f6f-4e27-a27c-096c373217af",
    "status": "sent",
    "registeredBy": "ceb518d8-6989-443f-aa75-197021ee139c",
    "registeredAt": "2026-10-13T01:31:00.000Z",
    "updatedAt": "2026-10-13T01:31:01.000Z",
    "processingState": "succeeded",
    "attempts": 1,
    "retryable": false,
    "errorCode": null,
    "quoteFact": {"quoteRound":"Q-20261013-01","sentAt":"2026-10-13T01:30:00.000Z","channel":"alibaba","evidence":"人工核实消息MSG-001"},
    "result": {"action":"updated","t1Updated":true,"verifiedAt":"2026-10-13T01:31:01.000Z","verifiedFields":{"craT1QuoteRound":"Q-20261013-01","craT1QuoteSentAt":"2026-10-13T01:30:00.000Z","craT1QuoteEvidence":"阿里平台｜人工核实消息MSG-001"}}
  },
  "replayed": false
}
```

HTTP状态：200为处理成功或成功重放；400为请求校验失败；403为无权限；404为目标不存在；409为同提交不同内容、同轮不同事实、旧版本/旧报价等冲突；422为已保存但被上游明确拒绝；503为暂不可用或可重试的已保存提交。已保存失败返回`value`，尚未接受的失败返回`error`。Twenty代理保留已保存失败结果，调用方必须检查`processingState`。

处理状态包括`pending`、`applying`、`succeeded`、`retryable`、`conflict`、`rejected`。成功结果动作包括`registered_only`、`updated`、`already_satisfied`、`recovered_readback`。

## 幂等、并发与恢复

- 提交编号为UUID主键，绑定规范化请求和登记人。同编号不同请求或不同登记人返回冲突。
- 成功提交重复请求直接返回原结果，不重新写入；此后人工修改也不会被旧提交覆盖。返回的是原处理结果，当前CRM值应通过读取接口确认。
- 同轮相同事实使用新编号登记也不重复PATCH；同轮不同事实拒绝。新轮实际发送时间必须晚于当前有效报价。
- 商机版本不符拒绝覆盖；保留所有其他字段，包括阶段、停止原因、约定日期和实际跟进时间。
- 写入前将恢复计划提交到SQLite。结果不明时先回读：匹配目标则确认成功；仍为原版本才允许重试条件PATCH；其他版本视为冲突。
- 进程崩溃后，用相同提交编号和完整原请求重试。不会重新计算写入前版本。无自动后台重试循环。
- 采用独立SQLite写锁串行执行，可跨线程/进程互斥，进程退出自动释放。全局串行适用于此MVP，等待锁最多20秒；高并发场景需要后续扩展。
- 同商机有尚未确认的发送提交时，阻止另一条已发送登记；可继续保存草稿。先查询并重试原提交，避免未确认结果被后续报价覆盖。
- 429、5xx、网络中断、读回暂不可用，以及401/403凭据问题保留为可重试。先修复原因，再重试原请求。冲突或非法输入需要重新核实并使用新提交编号，不能盲目重放。

本地SQLite与Twenty不构成跨系统事务；该机制以持久恢复计划和远端版本条件保证安全恢复，依赖Twenty在条件更新中实际执行版本过滤。生产启用前必须在独立测试商机核验真实实例的条件更新与回读，并验证报价专用Key的字段权限。

## 配置与启用

后台读取现有`deployment/review/.env`，将`quote-entry.env.example`中的变量合并后按实际授权填写。默认关闭；未配置时拒绝访问。

以下是后续已授权生产接入阶段的检查顺序，本轮不执行：

1. 核对生产 Workspace UUID、报价专用角色和实际字段映射，不能使用隔离实例角色 ID；角色不绑定 Admin。允许必要商机读取（接受 name 标识例外）、三个报价字段及必要 updatedBy 更新，继续拒绝其他业务字段、业务对象访问、删除和工作区管理。
2. 核对生产测试成员的 `workspaceMemberId` 与纯测试商机 UUID。`CRA_QUOTE_MEMBER_SCOPES` 为成员映射商机数组，首次配置仅列出该测试商机，不使用 `"*"`。星号代表应用显式授权全部商机，并非自动继承管理员或负责人权限。
3. 核对两个函数的实际部署调用地址、当前登录上下文、后台网络可达性、配置文件访问权限和报价数据库备份。SDK 本地构建通过不能替代 v2.45.0 已部署函数的身份验证。
4. 上述生产目标和角色经核对后，创建一把专用正式 Key，仅绑定该角色；Key 只写入 Python 后台。应用配置只包括独立通信 Token、工作区和成员范围，禁止配置 Twenty Key。默认报价开关继续关闭。
5. 发布与启用需后续单独授权。加载新后台代码需重启已有审核后台，安排受控窗口；启用时才改 `CRA_QUOTE_ENABLED`，不把填配置当作已上线。
6. 首次验收仅在生产 Workspace 的纯测试商机操作，验证认证上下文、跨成员/跨记录拒绝、三个字段更新和回读、版本冲突、name 不透传、Key/Token 不暴露，以及原 T1 扫描行为；通过后再扩大范围。

本轮未执行上述生产启用步骤，现有审核服务和T1继续按原配置运行。

## 备份与恢复

Twenty备份脚本发现报价数据库时，会调用Python标准库SQLite在线备份，输出`quote-registration.sqlite3`并加入校验和。锁数据库不需要备份或恢复。启动脚本所在WSL须有Python3；当前环境已检查备份脚本语法。

恢复前停止报价请求，使用经过校验的备份替换`records/quote-entry/registration.sqlite3`，保留报价环境配置（含机密的后台配置须单独安全备份）。恢复后重试未完成提交会先读取Twenty。若Twenty和登记库不是同一时刻的备份，出现版本冲突应人工核实，不强制覆盖。

## 测试与T1影响

测试结果见`docs/deployment/项目4-C-报价后端验收.md`。

2026-10-13 接入准备复核见 `docs/deployment/项目4-生产接入准备检查报告.md`：本轮 49 项 Python 报价测试、14 项应用测试（其中 6 项报价代理测试）通过，类型检查及本地构建通过。新增上游额外字段裁剪、必要字段缺失拒绝、业务/审计字段注入拒绝和携带凭据的重定向拒绝测试。隔离 Twenty 实验结果见 `deployment/twenty-permtest/verification/repair/权限修复验证报告.md`。

未修改T1规则、扫描、完成事件、任务权限或工作流配置。未知/未报价/草稿不会清空旧轮字段或关闭旧提醒；有效已发送事实将供原T1扫描使用，但本模块不直接创建任务。T1仍按原有到期日、负责人、停止原因和最终阶段判断是否创建提醒。人工停止或已成交商机即使登记已发送，也不会因此自动清空停止条件。
