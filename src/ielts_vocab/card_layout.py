"""Native Anki TTS and a compact reading layout; no remote assets."""

FRONT = """<main class="sheet">
<div class="eyebrow">词汇 · RECOGNITION</div>
<h1>{{RecognitionPrompt}}</h1>
<div class="pronunciation-grid">
<div class="pronunciation-row primary"><span class="badge">US · 主</span>
<div class="ipa">{{#IPA_US}}{{IPA_US}}{{/IPA_US}}</div>
<div class="audio default-audio">{{#PronunciationText}}{{tts en_US voices=Apple_Samantha,Apple_Samantha_(英语（美国）):PronunciationText}}{{/PronunciationText}}{{^PronunciationText}}{{tts en_US voices=Apple_Samantha,Apple_Samantha_(英语（美国）):Lemma}}{{/PronunciationText}}</div></div>
<div class="pronunciation-row"><span class="badge">UK</span>
<div class="ipa">{{#IPA_UK}}{{IPA_UK}}{{/IPA_UK}}</div>
<div class="audio">{{#PronunciationText}}{{tts en_GB:PronunciationText}}{{/PronunciationText}}{{^PronunciationText}}{{tts en_GB:Lemma}}{{/PronunciationText}}</div></div>
</div>
<p class="hint">回想它在阅读中的含义</p>
</main>"""

BACK = """<main class="sheet">
<div class="eyebrow">词汇 · RECOGNITION</div>
<h1>{{RecognitionPrompt}}</h1>
<section id="answer"><h2>核心含义</h2><p class="meaning">{{PrimaryMeaning}}</p></section>
{{#PrimarySentence}}<section><h2>原文例句 <span class="badge">US</span></h2>
<p class="sentence">{{PrimarySentence}}</p>
<div class="pronunciation default-audio">{{tts en_US voices=Apple_Samantha,Apple_Samantha_(英语（美国）):PrimarySentence}}</div></section>{{/PrimarySentence}}
{{#Collocations}}<section><h2>理解与用法</h2><div class="usage">{{Collocations}}</div></section>{{/Collocations}}
{{#IPA_Source}}<details><summary>音标来源</summary><div class="metadata">{{IPA_Source}}</div></details>{{/IPA_Source}}
{{#Sources}}<details><summary>查看来源</summary><div class="metadata">{{Sources}}</div></details>{{/Sources}}
{{#UserNotes}}<details><summary>备注</summary><div class="metadata">{{UserNotes}}</div></details>{{/UserNotes}}
</main>"""

# The deck must disable native autoplay: it otherwise queues both accents.
# Trigger the existing native replay control, preserving manual UK playback.
DEFAULT_AUDIO_SCRIPT = """<script>
(function () {
  var container = document.querySelector('.default-audio');
  if (!container || container.dataset.playRequested === 'yes') return;
  var button = container.querySelector('.replay-button, .replaybutton, .soundLink');
  if (!button) return;
  container.dataset.playRequested = 'yes';
  button.click();
})();
</script>"""
FRONT += DEFAULT_AUDIO_SCRIPT
BACK += DEFAULT_AUDIO_SCRIPT

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
.pronunciation-grid {display:grid;gap:8px;margin:12px 0;}
.pronunciation-row {display:grid;grid-template-columns:58px minmax(0,1fr) 42px;gap:10px;
align-items:center;padding:9px 10px;border:1px solid #e5e8eb;border-radius:10px;}
.pronunciation-row.primary {background:#f3f6fb;border-color:#ccd7ea;}
.ipa {font-family:"DejaVu Sans","Arial",sans-serif;font-size:17px;line-height:1.65;overflow-wrap:anywhere;}
.ipa-note {font-size:12px;color:#697585;margin:10px 0;}
.audio {display:flex;align-items:center;justify-content:center;}
.nightMode .pronunciation-row {border-color:#3b4552;}
.nightMode .pronunciation-row.primary {background:#2a3545;border-color:#526684;}
.nightMode .ipa-note {color:#aab6c6;}
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

CSS += """
.learning-extra {font-size:16px;line-height:1.8;}
.learning-extra p {margin:14px 0;}
.learning-extra summary {font-size:15px;min-height:44px;}
.usage small {font-size:12px;color:#697585;}
.nightMode .usage small {color:#aab6c6;}
"""
