# 本地邮箱采集

账号：wingcore2026@163.com；IMAP TLS993；授权码只放ACL保护的.env。
2026-10-11用户选择最近30天，因此首次读取服务器内部日期自2026-09-11起的收件箱及\Sent文件夹。该起点固定，增量由UIDVALIDITY和UID游标控制。

脚本：scripts/collect-mail.py，Python3.12标准库。只读EXAMINE、BODY.PEEK读取邮件头及MIME文字正文，不读取附件、草稿、垃圾箱或发送邮件。保留邮件头、回复链、原始MIME结构、正文与文件夹副本关系。HTML提取正文，不执行脚本或请求远程图片。超过1MiB的单个正文部分记录text_truncated；不能把截断内容当完整证据。

SQLite持久数据：records/chat-signal/mail.sqlite3；只保存到本项目。邮件Message-ID和内容摘要去重，文件夹UID副本独立登记；游标在成功持久提交后推进。UIDVALIDITY变化时重新扫描授权日期范围，同Message-ID异内容保留版本。回复链不自动等同客户或订单；尚未接模型和CRM。

状态：records/chat-signal/mail-status.json，包含最后运行时间、成功/失败、数量，不输出正文和密钥。失败保留原游标和已有数据。

计划任务CRA-Wingcore-Mail-Collector每分钟运行、登录补跑、重复触发不并发。当前Windows用户保持登录及电脑联网时运行；关机/休眠不会持续收取，恢复后补查。任务服务启动、账号读取、模型分析和CRM更新是独立步骤。

手动检查：
```powershell
& 'C:/Program Files/Python312/python.exe' 'K:/CRA客户项目/scripts/collect-mail.py'
Get-ScheduledTaskInfo -TaskName 'CRA-Wingcore-Mail-Collector'
```

注册脚本：scripts/register-mail-collector.ps1；授权码变更只修改.env，不写到脚本。备份需包含SQLite（使用SQLite备份接口以避免遗漏WAL）和私密配置；后续纳入全链备份验收。
