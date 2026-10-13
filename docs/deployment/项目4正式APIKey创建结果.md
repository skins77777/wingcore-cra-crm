# 《项目4正式API Key创建结果》

日期：2026-10-13，Asia/Hong_Kong。

**生产报价后台专用API Key已创建并配置到Python后台。唯一角色绑定、后台配置解析及Twenty只读认证验证通过；报价开关保持false。尚未具备直接执行报价登记测试的完整配置。**

## 1. Key创建结果

| 项目 | 结果 |
|---|---|
| 名称 | CRA Quote Entry Backend Production |
| Key ID（非Key内容） | 5097c241-d7e5-4494-91a5-c5b130bbbee7 |
| 创建时间 | 2026-10-13 05:03:03.569912 +08:00 |
| 有效期 | 90天 |
| 到期时间 | 2027-01-11 05:03:03.722 +08:00 |
| Workspace | YIHE |
| Workspace UUID | b7d89ec7-6e83-4216-8e1d-cf16feea5e27 |
| 当前状态 | 有效、未撤销 |

通过Twenty生产管理页面，在正常管理员登录后创建。创建表单保存前已将默认Admin改为正式报价角色，并设置90天有效期。没有先创建Admin Key再更换角色。

本报告及证据不包含Key内容、认证头或原始CRM业务响应。

## 2. Role绑定结果

| 项目 | 结果 |
|---|---|
| 绑定角色 | CRA Quote Entry Backend |
| Role ID | 7e982917-9d74-488a-857d-223d05f22a91 |
| 绑定数量 | 1 |
| Admin绑定 | 无 |
| 其他角色绑定 | 无 |
| 用户／Agent绑定 | 无 |
| 额外权限 | 未授予 |

只读数据库回查确认Key和角色属于同一YIHE Workspace。原角色的全局权限、42个对象配置、40个Opportunity字段配置和权限标记均与创建前一致，没有修改角色权限。

## 3. 配置状态

仅对deployment/review/.env增加以下配置：

- CRA_QUOTE_API_KEY：已配置新生产Key，不在报告中展示。
- CRA_QUOTE_ENABLED：明确为false。

原有其他配置键和值保持一致；配置文件访问权限未扩展。文件原有访问列表仅包含SYSTEM和现有本机账户。

使用与review_backend相同的配置解析方式验证：Key能从文件正确加载，且配置中的凭据ID及Workspace与新建Key一致。实际QuoteRemote适配器也可读取纯测试商机。service_from_config仍按关闭开关返回quote_module_disabled。

现有运行进程没有重启，本轮不声称运行中的后台已重新加载配置或报价功能已启动。

尚未配置：CRA_QUOTE_API_TOKEN、CRA_QUOTE_WORKSPACE_ID、CRA_QUOTE_MEMBER_SCOPES。本轮没有擅自补齐这些配置，也没有写入Twenty应用Secret。

## 4. 只读验证与安全检查

| 检查 | 结果 |
|---|---|
| 新Key读取生产纯测试商机 | HTTP 200，认证成功 |
| 读取Company | HTTP 400，PERMISSION_DENIED |
| 读取Person／联系人 | HTTP 400，PERMISSION_DENIED |
| 读取Task | HTTP 400，PERMISSION_DENIED |
| Python读取适配器 | 只返回固定六字段 |
| 报价功能开关 | false，模块拒绝启动报价服务 |
| 应用源码与构建产物检查 | 扫描47个文件，未发现该Key内容 |
| Twenty应用Secret | 指纹不变，未写入Key |
| 角色权限 | 与创建前一致 |
| 其他现有Key和绑定 | 保持不变 |
| 生产商机版本快照 | 保持不变 |
| 应用版本、默认角色及状态 | 保持不变，未发布 |

只读取测试商机“自动继承测试商机 20261012”，UUID为2e2b9f7e-b0c7-4f24-8bba-c4f3deba32de。没有提交POST、PATCH、DELETE到CRM对象接口，也没有调用报价登记接口。

Twenty原始读取仍返回六个目标字段加name，这是已知名称标识例外；Python适配器已丢弃name。实际后台读取保留：id、updatedAt、deletedAt、craT1QuoteRound、craT1QuoteSentAt、craT1QuoteEvidence。

本轮应用安全检查针对已生成的这个Key，不把变量名搜索当作唯一证据。Key内容只写入目标.env，未写入前端、应用变量、报告、证据JSON或日志。复制缓存和操作过程中的临时变量已清除；截图取自不显示Key内容的管理列表。

## 5. 是否可以进入报价功能测试

**Key创建与只读认证阶段完成，可以推进报价功能测试准备，但当前不能直接运行报价登记测试。**

后续仍需单独授权完成：

1. 配置独立通信Token、YIHE Workspace UUID及明确的一人一测试商机范围，两端一致，不使用星号。
2. 配置对应Twenty应用Secret，确认后台地址和认证函数实际调用地址。
3. 发布报价函数与入口、受控加载后台代码，并在获准时开启报价功能。
4. 首次只对纯测试商机验证登记、条件三字段更新、回读、冲突、安全重试和T1联动，再决定业务使用范围。

角色的名称读取、workspaceMember系统读取和创建/更新权限共用等Twenty限制继续有效，本轮没有修改核心或尝试创建商机。凭据到期前应安排续期；不应将90天有效期视为无限期运行配置。

本轮未开启报价、未发布应用、未写入真实或测试报价、未修改角色权限、未配置其他Secret、未重启后台。

## 6. 证据

deployment/review/verification/production-key/内保存非敏感证据：

- key-binding.json：Key ID、名称、时间、Workspace和唯一角色绑定。
- verification.json：配置加载、GET认证、对象拒绝、字段裁剪及不变项核对结果。
- config-change-check.json：确认.env只变更Key和关闭开关。
- before.json、after.json：只读状态快照，不保存Key内容。
- key-list.png：不含Secret的创建结果页面。
- verify_production_key.py：只读检查脚本，禁止重定向，不输出认证信息或原始CRM数据。
