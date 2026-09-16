"""Native Anki TTS and a compact reading layout; no remote assets or JavaScript."""

FRONT = """<main class="sheet">
<div class="eyebrow">词汇 · RECOGNITION</div>
<h1>{{RecognitionPrompt}}</h1>
<div class="pronunciation"><span class="badge">UK</span>
{{#PronunciationText}}{{tts en_GB:PronunciationText}}{{/PronunciationText}}
{{^PronunciationText}}{{tts en_GB:Lemma}}{{/PronunciationText}}</div>
<p class="hint">回想它在阅读中的含义</p>
</main>"""

BACK = """<main class="sheet">
<div class="eyebrow">词汇 · RECOGNITION</div>
<h1>{{RecognitionPrompt}}</h1>
<section id="answer"><h2>核心含义</h2><p class="meaning">{{PrimaryMeaning}}</p></section>
{{#PrimarySentence}}<section><h2>原文例句 <span class="badge">UK</span></h2>
<p class="sentence">{{PrimarySentence}}</p>
<div class="pronunciation">{{tts en_GB:PrimarySentence}}</div></section>{{/PrimarySentence}}
{{#Collocations}}<section><h2>搭配与用法</h2><div class="usage">{{Collocations}}</div></section>{{/Collocations}}
{{#Sources}}<details><summary>查看来源</summary><div class="metadata">{{Sources}}</div></details>{{/Sources}}
{{#UserNotes}}<details><summary>备注</summary><div class="metadata">{{UserNotes}}</div></details>{{/UserNotes}}
</main>"""

CSS = """.card {font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
font-size:19px;text-align:left;line-height:1.65;margin:0;padding:24px 18px;
background:#f5f5f2;color:#26303c;}
.sheet {max-width:640px;margin:0 auto;padding:28px;background:#fff;border-radius:16px;}
h1 {font-size:32px;line-height:1.3;font-weight:650;margin:12px 0 18px;overflow-wrap:anywhere;}
.eyebrow,h2 {font-size:12px;letter-spacing:.08em;color:#657182;font-weight:600;}
h2 {margin:0 0 10px;}.eyebrow {text-transform:uppercase;}
section {margin-top:24px;padding-top:20px;border-top:1px solid #e5e8eb;}
p {margin:0 0 10px;}.meaning {font-size:22px;font-weight:550;}
.sentence {line-height:1.8;}.sentence b {color:#526b9d;}
.pronunciation {display:flex;align-items:center;gap:10px;min-height:44px;}
.badge {display:inline-block;border-radius:5px;background:#edf0f6;color:#526b9d;
font-size:11px;padding:2px 7px;letter-spacing:.03em;vertical-align:middle;}
.replay-button svg {width:38px;height:38px;}.hint {font-size:14px;color:#7b8490;margin-top:16px;}
.usage {font-size:17px;line-height:1.85;}details {font-size:13px;color:#697585;margin-top:20px;}
summary {cursor:pointer;padding:8px 0;}.metadata {overflow-wrap:anywhere;font-size:13px;}
a {color:#526b9d;}.nightMode.card {background:#171c23;color:#e8edf3;}
.nightMode .sheet {background:#222a34;}.nightMode section {border-color:#3b4552;}
.nightMode h2,.nightMode .eyebrow,.nightMode details,.nightMode .hint {color:#aab6c6;}
.nightMode .badge {background:#354255;color:#d3e0f8;}
.nightMode a,.nightMode .sentence b {color:#afc5ef;}
@media(max-width:480px){.card{padding:12px 8px;font-size:18px;}.sheet{padding:22px 18px;}
h1{font-size:28px;}.meaning{font-size:21px;}}
"""
