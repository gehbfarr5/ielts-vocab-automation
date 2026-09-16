# 开源复用调研

核验日期2026-09-16。按本地需求（Mac截图、历史读取、可靠写入、词频）用GitHub CLI检索公共仓库、issues与源码；Anki接口交由一个只读研究子任务核对，主实现另行验证实际调用。不访问私人GitHub仓库。

| 候选 | 核验信息 | 决定 |
|---|---|---|
| [FooSoft/anki-connect](https://github.com/FooSoft/anki-connect) | 2079 Stars、235 forks；已归档，2025-11-04推送；Python；GPL-3.0-or-later | 只用其迁移声明，安装/代码以SourceHut实际上游为准 |
| [维护上游](https://git.sr.ht/~foosoft/anki-connect) | HEAD de6e6e1b8aaf4ae195eb1d1ff6db5409b99b2a3e，2025-12-05 | reuse v6接口；不在本仓库复制插件源码 |
| [rspeer/wordfreq](https://github.com/rspeer/wordfreq) | 1744 Stars、117 forks；2025-01-04推送；Python；代码Apache-2.0，数据另有署名/共享要求 | reuse已发布3.1.1；不是IELTS或义项频率，不打包数据文件 |
| [python-pillow/Pillow](https://github.com/python-pillow/Pillow) | 13814 Stars、2507 forks；2026-09-16推送；Python/C；HPND类许可证 | reuse解码、EXIF方向与像素处理，版本锁定 |
| [gorakhargosh/watchdog](https://github.com/gorakhargosh/watchdog) | 7412 Stars；2026-09-06推送；Apache-2.0 | 暂不依赖；首版周期扫描直接补漏，日后优化唤醒延迟再引入 |

频率资源最近活动较久，不冒称持续更新语料。Star为时间点记录，仅辅助成熟度；接口适配证据优先。SQLite事务/应用outbox为本地特有逻辑，未发现比标准库更贴合的小型现成实现，采用最小自研并做并发、崩溃测试。

## 关键接口证据

- [AnkiConnect README](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/README.md) 与 [源码](https://git.sr.ht/~foosoft/anki-connect/tree/master/item/plugin/__init__.py)：`getReviewsOfCards`使用整数卡ID，记录无排序保证；不要照搬README字符串ID示例。
- [历史读取问题记录](https://github.com/FooSoft/anki-connect/issues/378)：历史接口使用存在误用风险；以源码和本地实测为准，issue本身不是已修复证明。
- [Anki revlog类型](https://github.com/ankitects/anki/blob/main/rslib/src/revlog/mod.rs)：排程/人工记录不能算实际首次学习。
- `updateNoteFields`无CAS且忽略不存在的字段，不依赖Undo；必须预检模型、字段比较、持久快照、读回。
- `sync`不能证明移动端已接收，完整同步冲突必须单列。
- [官方卡片生成](https://docs.ankiweb.net/templates/generation.html)：Context用条件模板，固定sense槽，避免空卡与重新使用旧历史。
- [Codex非交互接口](https://learn.chatgpt.com/docs/developer-commands#codex-exec)：结构化输出和图片输入；[公开配置schema](https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json)用于禁用外部工具。适配器尚未通过真实云调用，不把接口存在当已部署。

Anki程序实际安装版本25.09.4，外层launcher标识25.09、launcher的目标依赖26.09.2与实际安装不一致。本轮使用已有25.09.4隔离测试目录验证；没有为本项目升级用户Anki。
