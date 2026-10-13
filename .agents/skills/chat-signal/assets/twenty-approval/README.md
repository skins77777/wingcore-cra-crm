# Twenty 待审核应用 · CRA 客户版

本目录随 chat-signal 分发，提供可构建的 Twenty 应用源码：侧边栏“待审核”、审核列表与详情、通过/拒绝、备注、候选选择、决定及执行状态。审核原因、字段和选项来自客户后台，不固定行业、对象或审核类型。

先完成 crm-fde 和 chat-signal 的业务规则确认，再按 [配置与验收指导](../../references/13-review-app.md) 配置客户的规则和应用。业务规则留在共同档案，客户不需要编辑 TypeScript 或填写 API 契约。

## 组成与边界

- Twenty 中的页面和两个登录态服务端函数；前端不接触外部 Token。
- 客户后台按 [接口约定](API.md) 提供审核事项、保存决定和衔接执行；可以适配已有服务，不要求新的数据库或云服务。
- 当前 v1 源码只提供业务审核；独立系统异常区、复制排查信息、自动刷新/新事项提示、侧栏计数或全局铃铛尚未包含。实施时按 [页面布局与通知要求](../../references/13-review-app.md) 在客户副本补齐并验证，不能把错误日志塞成业务审核来冒充这些功能。
- 页面不会自行判断哪些变更需要审核，不直接写 CRM，也不内置消息接入或自动化执行器。安装后缺少后台时显示读取错误，不能假装“没有待审核事项”。
- 作者系统的同步按钮、数据库直连、工作区、成员 ID、记录 ID、域名、三类审核白名单及测试记录均未随包复制。

## 本地准备

把本目录源码复制到客户项目的 `integrations/twenty-approval`（已有目录先比较），在副本中安装和构建，保留原 Skill 资产用于版本比较。Node.js >=24.5，SDK 固定 2.41.0；目标 Twenty 版本的兼容性仍需现场验证。

```sh
npm ci
npm test
npm run typecheck
npm run build
```

`package-lock.json` 锁定依赖；构建产物在本地生成，不把 node_modules、构建缓存或客户配置放回通用包。按实际目标核实 CLI 的 `auth`、`remote`、`plan`、`apply` 帮助，再预览和非删除式发布，不使用会移除未声明资源的同步。

应用元数据使用本客户版的新身份，与作者旧 App 分离。同一份安装的升级保持标识稳定；如果在同一 Twenty 实例给另一个注册所有者安装源码副本，首次注册前由 Codex 为整套定义生成一致的新标识并保存映射，不能在每次升级时重生成。[官方注册与发布说明](https://docs.twenty.com/developers/extend/apps/operations/publishing)

## 应用变量

| 变量 | 配置来源 |
|---|---|
| CRA_REVIEW_API_URL | 客户审核后台的 HTTPS 根地址，可含路径前缀；不能含凭据、查询或锚点 |
| CRA_REVIEW_API_TOKEN | 后台签发且绑定客户工作区的服务端 Token |
| CRA_REVIEW_WORKSPACE_ID | 客户后台实际工作区 ID，使用字母、数字、下划线或连字符 |
| CRA_REVIEWER_MEMBER_IDS | 该 Twenty 工作区中获授权审核人的 workspaceMemberId，逗号分隔；不是全局 user ID |

四项均声明为 Secret，由目标应用设置注入服务端。没有预设值或旧环境回退。页面展示的具体事项与决定权限还要由后台按成员、规则与数据范围校验。规则调整通常只改共同业务档案和后台配置，无需重编译页面。[官方应用配置与 Secret 说明](https://docs.twenty.com/developers/extend/apps/config/application)

## 来源与许可记录

按项目所有者本次指令，将其“待审核”应用纳入 CRA 套装。页面布局及导航定义沿用已有实现的结构，其余客户版代码在 CRA 中按通用审核请求重新整理。应用身份重新生成；源项目及作者生产环境未修改。

保留私有分发属性 `private: true`、`UNLICENSED`；本次纳入客户套装不宣称公共开源许可。第三方依赖的许可随其 npm 包保留。
