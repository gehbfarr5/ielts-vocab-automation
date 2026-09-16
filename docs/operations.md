# 运行与恢复

## 私有配置

`ielts-vocab init` 创建仓库外0700数据目录、0600配置与随机收件令牌，不覆盖已有配置。

- `allow_cloud_images=false`：默认仅本地 OCR。云图像范围与模型服务批准、实际调用验证后才能开启。
- `calibration_verified=false`：默认 ACCEPT 降为 DEFER；必须基于独立真实样本评估设置，不能为了放行测试随意改为true。
- `writes_enabled=false`：默认不改 Anki。
- `legacy_inventory_reviewed=false`：旧未学库存及模型映射未验收则禁止写入。
- `anki_profile`：需使用 API 返回的真实名称，不能猜英文默认值。
- `anki_deck`：专用受管牌组。
- `anki_key_file`：本地0600密钥文件路径。
- `timezone`/`rollover_hour`：必须与实际学习日一致。
- `max_analyzer_calls_per_24h`：默认10次，失败调用也计数；不等于货币费用上限。

## Anki

官方 AnkiConnect 安装编号2055492159，安装后重启。保留127.0.0.1监听，建议设置apiKey。生产资料库先备份。不要复制测试资料库覆盖正式资料库。

```sh
uv run ielts-vocab doctor
uv run ielts-vocab history --query 'deck:"IELTS"'
```

历史保存到私有目录，不进Git。`write-pending` 仍需所有启用门槛和新鲜的学习日状态。它不会自行填造复习/同步事实。恢复日当日不能解除；次日可以重新设置。

## 服务

```sh
uv run python deployment/install_local.py
launchctl print gui/$(id -u)/local.ielts-vocab.worker
```

用户会话的 worker 每60秒扫描一次；单写入进程锁，服务重启可重扫。launchd不会让睡眠的Mac持续处理。收件服务认证后才读图，不开放公网。首次启动及每分钟作业只在新图到来时分析，重复图不重复调用模型。

停止：

```sh
launchctl bootout gui/$(id -u)/local.ielts-vocab.worker
launchctl bootout gui/$(id -u)/local.ielts-vocab.intake
```

这只停止服务，不删除词库/历史/文件。配置默认 shadow，停止监听与关闭写入可快速止损。

## 故障处理

- `awaiting_analyzer`：本地OCR完成，等待已批准的分析器；不是已入卡。
- `error`：查看私有events/错误阶段；修复原因后 `retry <submission-id>`。最多3次，不自动静默降级。
- `write_uncertain`：保留预算。按EntryID与期望哈希读回，不能删除预留后盲重建。
- `written`：Mac已经读回正确，尚未请求同步。
- `sync_requested`：同步API返回，不代表iPad/媒体已完成。
- 原生Anki提示全量上传/下载：停止并核对备份和权威端，不自动选择。
- 用户修改受管字段：保存差异并暂停该项；UserNotes始终保留。

截图暂存最多约1GiB、5000个唯一输入，不自动删除私人原图；达到上限显式拒收，后续需要人工审阅保留政策。日志轮转和定期归档尚未实现，常态部署前需补齐。

## 回滚

事件日志包含写前字段与意图。当前提供可审阅快照，没有自动整库回滚命令；恢复受管字段前必须确认没有更新的用户修改。已经复习的新卡不能随意删除。恢复整个Anki资料库可能影响其他设备，属于另行选择的操作。

## 原生TTS验收版
Recognition模板采用en_GB原生TTS，正面读PronunciationText（空时读Lemma），背面读PrimarySentence。新增PronunciationText位于字段末尾；音标尚未加入，TTS不等于IPA。排版资源位于card_layout.py，无远程资源。
2026-09-16仅对Mac独立测试库执行模型备份、追加字段、模板更新，并更新3张待确认卡的发音文本/原句强调；卡片ID和调度读回一致。模板属于Note Type，同模型旧测试卡也继承排版；未删除或新增卡。目标样本缺少完整OCR句尾已按下一行证据补齐。用户需在预览/复习窗口验证词条与句子的播放和视觉效果，编辑器字段列表不能代表卡片排版。
已有其他资料库必须显式追加字段并备份模板后才能使用新版本；setup继续拒绝未经迁移的旧字段结构。映射的受管字段快照也需审查，不能为通过检查而覆盖用户编辑。正式自动写入仍关闭。恢复时使用私有pre-tts-backup.json中的原模板/样式/字段内容；不要删除Note或重置学习记录。
