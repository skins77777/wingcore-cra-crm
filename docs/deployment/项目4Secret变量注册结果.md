# 项目4 Secret变量注册结果

日期：2026-10-13（Asia/Hong_Kong）。

**结果：三个报价 Secret 变量已正式注册到 YIHE 生产“待审核”应用。生产应用版本仍为 0.1.2；没有发布报价组件或函数，没有配置真实 Secret 值，报价仍关闭。**

## 1. 注册结果

目标 Twenty：`http://localhost:3000`。

Workspace：YIHE，UUID `b7d89ec7-6e83-4216-8e1d-cf16feea5e27`。

应用 ID：`1246cb6c-f326-443a-a3b6-77d5a6b081f1`。

应用 universalIdentifier：`9f668dec-9996-41d9-8240-5656232210a6`。

本轮通过 Twenty 官方元数据接口执行变量定义注册，使用非删除模式。实际提交的清单以生产已保存的 0.1.2 清单为底稿，完整保留既有资源声明，仅加入三个 Secret 定义；没有使用包含尚未上线报价组件及函数的本地完整构建清单。

执行前重新计算只读计划，执行结果也均为：新增 applicationVariable 3 项，修改资源 0 项，删除资源 0 项。没有上传任何应用文件或安装完整报价应用。

正式注册完成时间：2026-10-13 05:28:26.918（Asia/Hong_Kong）。

## 2. 新增变量列表

| 名称 | 正式变量 ID | 属性 | 存储类型 | 值配置 |
|---|---|---|---|---|
| CRA_QUOTE_API_TOKEN | d701be64-1ca2-4cdc-bb3b-d0aff69e2bb3 | Secret，isSecret=true | TEXT | 空，未配置 |
| CRA_QUOTE_WORKSPACE_ID | 67b76d12-663a-45e1-844d-bbcd01bf5116 | Secret，isSecret=true | TEXT | 空，未配置 |
| CRA_QUOTE_MEMBER_SCOPES | b6d67d29-70dc-423c-ac72-3ce52b3e1c58 | Secret，isSecret=true | TEXT | 空，未配置 |

这里 Secret 是保密属性，TEXT 是存储字段类型。正式 ID 来自创建后的只读回查，不使用预览生成的拟创建 ID。

三项 universalIdentifier 与本地声明保持一致。生产变量页面也已显示三个新变量，值输入框均为空。

没有添加 `CRA_QUOTE_API_KEY`。该 Key 继续仅保存在 Python 后台，已有 Key 清单及角色绑定未变。

## 3. 原有变量保护检查

原有四项变量仍存在：

- CRA_REVIEW_API_URL
- CRA_REVIEW_API_TOKEN
- CRA_REVIEW_WORKSPACE_ID
- CRA_REVIEWER_MEMBER_IDS

原有变量的定义、Secret 属性、ID、存储指纹及更新时间均与注册前一致，没有修改其值。整个 Workspace 其他既有应用变量也保持不变。

后台 `.env` 文件与所有原应用源码、Python 模块的指纹均未变化。`CRA_QUOTE_ENABLED` 仍为 `false`。

## 4. 应用资源变化检查

创建后只读回查的 26 项检查全部通过：

- 生产应用版本与注册可用版本均保持 0.1.2。
- `cra-approval-center` 与所有现有前端组件记录指纹未变。
- 所有现有服务端函数记录指纹未变，没有新增或发布报价函数。
- 原有角色、对象权限、字段权限、角色绑定和 API Key 清单未变。
- T1 相关商机字段及对象快照未变。
- 商机版本与删除状态快照未变；没有调用商机更新、删除或报价登记接口。
- 已保存的生产应用清单只增加三个变量定义，其他资源声明完整保留。
- 其他已安装应用的 ID、版本、更新时间及默认角色快照未变。
- 报价登记数据库仍未生成。

需要记录的 Twenty 官方流程行为：应用记录及应用注册记录的更新时间发生变化；注册记录的来源标记从 `tarball` 改为 `local`。已安装应用自身的来源仍为 `tarball`，版本、默认角色、依赖校验和、组件和函数没有改变。注册展示信息、OAuth 设置和原资源声明也保留不变。本轮没有改动 Twenty 核心来抑制该来源标记变化。

## 5. 是否可以进入报价应用发布阶段

**可以进入报价应用发布的预览与审查阶段，三个 Secret 定义缺失的阻塞已经解除。**

当前尚未发布报价组件、菜单和函数，三个生产 Secret 值仍为空。后续需要分别完成安全填值与两端一致性验证、完整报价应用变更范围预览、发布授权及后台配置加载安排。不能将本轮“仅新增三个变量”的结果作为完整报价应用发布验收。

继续保持 `CRA_QUOTE_ENABLED=false`。本报告不代表报价已上线或通信已验收，也不授权功能开启、报价登记或商机写入。

## 证据位置

目录：`K:/CRA客户项目/deployment/review/verification/quote-variable-registration/`。

- `registration.manifest.json`：保留生产资源声明的注册清单，不含真实 Secret 值。
- `dry-run-actions.json`、`registration-actions.json`：预览和执行的三项新增结果，已移除值内容及拟创建 ID。
- `before.json`、`after.json`、`verification.json`：注册前后只读快照、正式变量 ID 和 26 项检查。
- `variables.png`：生产变量页面截图，仅显示三个空值报价变量与应用上下文。
- `apply-dispatched.json`：防止重复执行标记；本轮只提交一次注册请求。

![生产应用三个报价Secret变量，值保持为空](../../deployment/review/verification/quote-variable-registration/variables.png)
