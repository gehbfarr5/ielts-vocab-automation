# IELTS Vocabulary Automation

从 Goodnotes 三色截图收集词汇，用可追溯的筛选与双预算控制 Anki 新卡。

**v0.1 是开发预览：本地收件、OCR、队列与 Anki 安全写入已实现；默认 shadow 模式，不会自动写入个人词库。尚未完成正式 Level D 验收。**

- 金黄 `#E6C162`：unknown；豆沙粉 `#BF8486`：partial；灰蓝 `#6E83B0`：phrase/context unclear。见[配色规范 v2](docs/mark-colors.md)。
- 主动共享图片或将图片放入固定 iCloud 文件夹，两种入口共用队列。
- SQLite 持久收件、SHA-256 去重、提交 ID 重放保护、失败状态与审计事件。
- Apple Vision 在 Mac 本地识别英文，颜色区域提供辅助证据。
- Agent 输出严格校验；CEFR/学术词表没有证据时明确缺失，拒绝杜撰。
- 同 lemma 共用 Note；默认 Recognition，最多两个固定 Context 槽；已有槽不替换考点。
- 核心词和卡片分别限制；恢复日锁定、跨日保留未学预留、并发额度事务。
- Anki 字段写前比较、写后读回，超时不盲目重复创建；不修改调度或复习历史。

## 快速开始（macOS）

需要 Python 3.12+、uv、Apple 命令行开发工具；Anki 集成另需官方 AnkiConnect。

```sh
uv sync --locked
uv run ielts-vocab init
uv run ielts-vocab build-ocr
uv run ielts-vocab doctor
uv run ielts-vocab ingest /absolute/path/to/screenshot.png
uv run ielts-vocab process
uv run ielts-vocab status
```

默认数据目录：`~/Library/Application Support/IELTSVocab`。使用 `--root /absolute/private/directory` 可建立独立测试环境。配置、令牌、图片、数据库、日志全部位于仓库外。示例不包含凭据。

默认会完成本地 OCR，然后进入 `awaiting_analyzer`。启用云分析需先确认数据处理范围与可用模型服务；本版本有 Codex CLI 适配器，但尚未完成真实云调用验收。它使用系统现有登录，不读取或复制凭据，不假定 ChatGPT 订阅等于 OpenAI API 余额。不要仅修改一个开关就把未验收流程接到正式资料库。

## 实施状态

| 能力 | v0.1 状态 |
|---|---|
| 文件收件、图片完整性校验、重复抑制 | 已实现并测试 |
| 认证 HTTP 收件（loopback） | 已实现；未认证请求拒绝 |
| 原生本地 OCR | 已在合成三色样本运行 |
| iCloud 定时扫描、重启补扫 | 已实现；移动端到达时延未验收 |
| Agent 结构化适配与证据门 | 已实现；云调用/真实精度待验证 |
| Anki Note/Context 与读回 | 已在独立 Anki 25.09.4 + AnkiConnect v6 实测 |
| 历史读取、首次真实作答识别 | API 已核对；统计逻辑测试通过 |
| 核心词/卡/Context 额度账本 | 已实现；不代表离线移动端全局学习限制 |
| 自动学习日政策、旧词库映射、完整 Level 4 | 待接通真实数据与规则验收 |
| 固定相册原生监听、移动端同步验收 | 尚未实现/验收 |

## 运行与测试

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
```

`deployment/install_local.py` 安装用户会话下的本地收件与每分钟扫描服务；它不启用云分析或正式词库写入。安装前阅读 [运行手册](docs/operations.md)。本地服务不向公网监听。

## 文档

- [需求与架构](docs/architecture.md)
- [Shortcut 与收件接口](docs/shortcut.md)
- [运行、配置与恢复](docs/operations.md)
- [验收记录与剩余工作](docs/acceptance.md)
- [开源调研与复用决定](docs/research.md)
- [隐私与发布边界](SECURITY.md)

公开仓库用于版本管理。尚未选择开源许可证；公开可见不等于授予任意再分发许可。运行依赖遵守各自许可证；本项目不打包教材、词典或 AnkiConnect 源码。
