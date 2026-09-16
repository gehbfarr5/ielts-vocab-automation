# Anki词汇卡排版、音标与发音调研

日期：2026-09-16。范围：只读调研，不安装插件、不修改卡片和模型、不调用付费语音。

## 当前问题与约束

实际读取Mac独立测试库的IELTS Lexeme v1：正面只有RecognitionPrompt，背面由FrontSide、释义、原句、搭配经hr/br直接拼接。CSS所有文本统一22px，无标题/正文/辅助信息层级。当前模型没有IPA或音频字段；Sources/UserNotes也未在模板呈现。这解释了内容堆叠的结构问题，本轮不是设备截图视觉验收。

目标：iPad/iPhone为主要复习端，Mac生成/维护；单词和固定搭配兼容，保持已有Note/Card ID及学习历史，一词默认一张Recognition；不因添加语音额外增加卡片。个人原文、卡片数据与音频不进入公开仓库。当前实际测试Anki为25.09.4；候选支持声明不能代替实机验证。

## 搜索与证据

用gh搜索anki templates、anki english、hypertts、awesomeTTS、anki ipa，再读取仓库README、许可、代码树、维护日期和相关issues；以Anki官方文档核对移动发音和媒体同步。查询集中在同一Anki工作流，本轮未启用子代理，避免重复检索。Stars/forks为检索时快照。

| 项目 | Stars / forks | 许可与最近推送 | 匹配与处理建议 |
|---|---:|---|---|
| [Prettify](https://github.com/pranavdeshai/anki-prettify) | 535 / 26 | MIT；2024-08-10；SCSS | 最适合参考留白、响应式、浅深主题。adapt简洁CSS和层级，不整包导入覆盖现有模型。README明确测试Mac/AnkiDroid/AnkiWeb，未列AnkiMobile实测。 |
| [Anki Oxford Dictionary](https://github.com/thanhdxuan/anki-oxforddictionary) | 2 / 0 | MIT；2025-04-28；HTML | 字段包含Word、IPA、WordType、Audio，贴合英语卡；只参考信息结构。个人项目证据弱；避免其远程URL/本机绝对路径媒体做法，以及打字/随机挖空功能。 |
| [ankglish](https://github.com/UltiRequiem/ankglish) | 5 / 0 | MIT代码；2026-09-12；Python | 最接近“IPA+词性+离线音频+例句”的整体案例。adapt媒体打包/来源记录；项目较新，来源文件仍列待固定provider，不当成熟整套依赖，不导入大型词库。 |
| [HyperTTS](https://github.com/Vocab-Apps/anki-hyper-tts) | 282 / 47 | GPL-3.0；2026-09-13；Python | Mac端生成/保存单词或句子音频，保存型音频可同步移动端。可选独立插件或参考架构；不复制GPL代码到项目。部分provider需密钥/费用，插件开源不代表服务免费。 |
| [Wiktextract](https://github.com/tatuylonen/wiktextract) / [Kaikki](https://kaikki.org/) | 1268 / 117 | 核心MIT，部分测试CC-BY-SA/GFDL；2026-09-14；Python | 结构化词条、读音、音频链接的候选来源。优先使用发布数据的小范围索引；不自己解析全部维基词典。词典数据与音频逐项保留许可/归属，与代码许可分开。 |
| [Phonemizer](https://github.com/bootphon/phonemizer) | 1571 / 202 | GPL-3.0；2026-08-04；Python | eSpeak后端可生成IPA，适合机器转写候选。不作为词典音标真值；上下文异读、弱读与方言需核验，也需额外后端依赖。 |

其他候选：[AwesomeTTS旧库](https://github.com/AwesomeTTS/awesometts-anki-addon)503 Stars已指向[Vocab-Apps维护库](https://github.com/Vocab-Apps/anki-awesome-tts)78 Stars /14 forks，GPL-3.0，2025-08-16；优先评估更新更近的HyperTTS。[Free Dictionary API](https://github.com/meetDeveloper/freeDictionaryAPI)3603 Stars/345 forks，GPL-3.0，2023-11-27；提供phonetics/audio结构，但本机对3个测试词/搭配请求均403，覆盖率和可用性没有验证，避免作唯一依赖。不能从403断言词不存在。

### 可查看的外观参考

- [Prettify Minimal截图](https://github.com/pranavdeshai/anki-prettify/blob/main/res/images/minimal-cover.png)：README提供静态示例，未验证独立实时演示。
- [Oxford式卡片截图](https://github.com/thanhdxuan/anki-oxforddictionary/blob/main/images/screenshot.jpeg)：静态示例，仓库有index.html；未验证独立在线演示。
- [ankglish截图](https://github.com/UltiRequiem/ankglish/blob/main/media/screenshot.png)：README静态示例，未验证独立在线演示。

这些是参考链接，本轮未运行或在设备上验收第三方模板。

## 推荐的两阶段路线

A：首版推荐“简洁自有模板+Anki原生TTS+有来源IPA”。改动较少，无需额外桌面语音插件；Mac/iOS可用系统语音。选择同一口音方向，但各设备声音可能不同，需提前下载所选系统语音并验证离线播放。TTS不会自动补出可靠IPA。

B：如要求多端音色一致，采用“同一模板+预生成MP3+有来源IPA”。Mac生成一次并写入collection.media，用标准sound字段同步；可评估HyperTTS或现有Python调用合适语音提供者。多一个生成和媒体同步阶段，但移动端不需要该桌面插件。必须试听固定搭配和异读词；音频缺失显式标记，不悄悄换声音。

推荐先A验证排版与学习体验，再决定是否升级B。若一开始明确要求同一音色和可搬运的离线音频，可直接B。不能把实时远程音频链接当离线媒体，也不能把Mac文件绝对路径写到手机卡片。

## 建议排版（方案，未实施）

正面：大号目标词/完整搭配；下方小号词性；音标与播放控件同一行，明确UK/US。默认不放中文答案和整段背景。发音建议先手动点播，是否自动播放按用户偏好，不生成额外听力卡。

背面：①当前义项中文核心释义；②一条原文例句，目标词加粗，例句音频独立按钮；③最多两条搭配/一句必要辨析；④来源、个人备注折叠在底部。Agent决策日志、内部ID、分数不塞入主学习区。空字段不显示空标题。正文单栏、行宽受限、长短语换行；手机窄屏和深色模式分别验收。

金黄/灰蓝/橄榄绿仅用于小标记提示原学习状态，不把整张卡背景染色，不与正文强调混用。

## IPA与音频的数据策略

新增方案字段：PronunciationText、IPA、PronunciationLocale、WordAudio、SentenceAudio、PronunciationSource；具体迁移设计另行实施。保留原Lemma/核心计数及Context槽，不为了换排版删除再建Note。

单词：选与当前词性/义项一致的词典IPA和同口音音频；同形异音如record必须区分词性。词典未提供时明确缺失，不让Agent凭空写入权威音标。

固定搭配：优先查完整词条；无整条转写时可显示有证据的关键词IPA，整条TTS单独提供。机器整句IPA必须显式标“机器转写待核验”，不建议第一版默认展示。one’s/someone等占位表达应定义可读PronunciationText，所展示IPA必须对应实际读出的文本，避免屏幕与声音不同。

单词音频与例句音频分开；字典原录音/机器合成标明来源。商业词典网页上能播放不等于允许批量提取或公开再分发；开源模板许可也不授予其示例媒体版权。仓库仅保存代码、模板、无个人数据的示例，媒体留用户Anki资料库。

## 验收与后续确认

用当前3张卡做样板，先确认前后层级，再迁移：Note/Card ID不变；只增加字段和样式；无新卡倍增。IPA与词性/口音一致；词头与例句分别播放；翻面不意外重复播放；iPhone窄屏/iPad横竖屏/深浅模式无截断；媒体方案B需完成媒体同步并离线播放。迁移前备份模型字段/模板，失败恢复模板而非整库覆盖。

待用户选择：英音/美音主口音；手动播放或自动播放；先原生TTS还是预生成音频。当前只给推荐，不安装、不修改现有卡。

官方依据：[原生TTS](https://docs.ankiweb.net/templates/fields.html#text-to-speech-for-individual-fields)、[AnkiMobile语音](https://docs.ankimobile.net/tts.html)、[媒体存储](https://docs.ankiweb.net/media.html)、[媒体同步完成条件](https://faqs.ankiweb.net/media-files-may-take-time-to-sync.html)、[HyperTTS功能](https://www.vocab.ai/hypertts)、[ankglish内容许可边界](https://github.com/UltiRequiem/ankglish/blob/main/SOURCES.md)。

结论：方案证据较充分；实际设备排版、音质、IPA覆盖率未验收。调研完成；修复轮数0；澄清0；耗时、模型强度、可用额度未知。

## 2026-09-16：美音优先与双口音音标

用户选择美音为主口音，保留英音。Recognition 正面采用两行 US / UK：口音标签、对应音标、原生 TTS 按钮；例句使用 en_US。音标来源折叠在背面，避免挤占释义和例句。缺少已核验音标时显示“音标待核验”，不能由拼写猜测后自动填入。

当前验收牌组使用单独克隆的预设，关闭自动播放，避免英美两条原生 TTS 连播；共享默认预设及学习参数保持原值。两个按钮均可点播，US 排第一。此设置仅应用于当前验收牌组，未来正式牌组需要显式沿用。

单词可以显示完整词典音标；固定搭配若没有可靠的整条音标，按词展示关键词音标，并注明“关键词音标；播放按钮朗读完整搭配”。不得把拼接的单词音标称为已核验的搭配连读转写。词典音标与合成语音来自不同系统，不承诺逐音完全相同。

新增字段：IPA_US、IPA_UK、IPA_Note、IPA_Source。复用 Anki 原生 TTS，不新增音频下载器或远程播放脚本。既有 Note 原位扩展，保留 Note/Card ID 和复习历史；迁移前的字段、模板、样式、牌组预设及卡片快照仅保存在私有运行目录。自动分析尚不填充这些音标字段；后续应接入可核验的词典来源并保留出处。

验证：三张现有验收卡已读回核对字段，正面生成两个播放标记、背面一个例句播放标记；原字段、ID、调度及复习计数保持不变，共享预设未变。实际移动端排版、语音与同步仍由后续实机验收确认。

### 修订：仅单词音标；明确选择美音声音

用户验收发现搭配音标影响排版，因此取代上面的关键词音标方案：仅单词填写 IPA；固定搭配/词组的 IPA_US、IPA_UK、IPA_Note、IPA_Source 留空，不显示待核验占位文案，保留双口音播放按钮。

美音听感异常的本地选声原因：Anki 25.09.4 的 MacTTSPlayer 在未指定 voices 时匹配首个语言相符的声音；本机 `say` 列表首个 en_US 是 Albert，en_GB 是 Daniel。通过实际 Anki 类调用核验，空偏好选择 Apple_Albert，显式偏好选择 Apple_Samantha。所有美音标签改用 `voices=Apple_Samantha`，涵盖正面及例句。未修改全局系统音量或语速，UK 保持原样。

证据：[Anki TTS 实现](https://github.com/ankitects/anki/blob/b3c23522d1e3cecdb2a2f999aa8cb32396fdb8b1/qt/aqt/tts.py)、[官方选声说明](https://docs.ankiweb.net/templates/fields.html#text-to-speech)。本次使用 GitHub code 搜索与本机安装源码，无需多代理或新依赖。复用原生 voices 配置；不采用预生成音频，因为本地选择错误已可直接修正。未能通过源码证明用户感知的响度差已消除，需要重新试听。其他设备若没有指定声音，Anki 原生会退回语言匹配，移动端选声需要单独验收。

三卡读回与 50 项测试通过；两张搭配音标清除、单词音标保留、播放控件存在、调度字段不变。迁移前备份及迁移后读回均在私有 acceptance 目录。回滚使用 pre-samantha-backup.json 恢复模板与相关字段。

### 默认仅自动播放美音

用户保留 Samantha，要求 US 自动、UK 手动。采用模板触发现有原生美音按钮的方式：验收牌组关闭 Anki 全量自动播放；正面脚本仅点击 `.default-audio` 中的 US 控件一次，UK 控件不属于此容器。背面例句同样仅使用美音。不得开启牌组全量自动播放，否则与模板触发叠加。此模板依赖牌组设置；其他使用同一模型的牌组也须禁用全量自动播放后才能保证行为。

方案对照：继续原生 TTS 加定向触发改动小；预生成双音频可独立控制，但增加媒体生成与同步，暂不采用。参考 [Anki 论坛选择性自动播放讨论](https://forums.ankiweb.net/t/disabling-audio-autoplay-for-certain-fields/6318/3)，本机 reviewer/sound 源码确认原生按钮经 `play:q:index` 点播。此为模板方案，移动端仍须验收，不声称所有客户端行为一致。

本机系统声音枚举目前将 Samantha 显示为本地化名称，故 voices 同时列出 Apple_Samantha 与 Apple_Samantha_(英语（美国）)，均明确指定 Samantha。三卡模板及设置读回通过，调度记录未变；脚本控制测试确认仅触发默认控件一次，50 项现有测试通过。实际 Anki 翻面播放听感与移动端待用户验收。备份在私有 acceptance/pre-selective-autoplay-*.json。
