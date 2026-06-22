"""
anki_export.py
Генерирует .apkg колоду Anki из данных GPT для японских предложений.

Зависимости:
    pip install genanki

Использование:
    from anki_export import create_anki_deck
    from pathlib import Path

    # Только .apkg файл:
    create_anki_deck(output_dir=Path("my_project"), gpt_output_data=[...])

    # Импорт через AnkiConnect (Anki должен быть запущен с установленным аддоном):
    create_anki_deck(output_dir=Path("my_project"), gpt_output_data=[...], ankiconnect=True)

    # Кастомный адрес AnkiConnect:
    create_anki_deck(..., ankiconnect=True, ankiconnect_url="http://127.0.0.1:8765")
"""

import re
import json
import base64
import hashlib
import urllib.request
import urllib.error
from pathlib import Path

import genanki


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def sanitize_filename(text: str, max_length: int = 512) -> str:
    """Удаляет недопустимые символы для имени файла (Windows)."""
    text = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_length:
        text = text[:max_length]
    return text


def _stable_id(seed: str) -> int:
    """Детерминированный числовой ID из строки (для модели/колоды)."""
    return int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)


# ──────────────────────────────────────────────
# AnkiConnect
# ──────────────────────────────────────────────

class AnkiConnectError(RuntimeError):
    """Ошибка при работе с AnkiConnect."""


def _ankiconnect_request(url: str, action: str, **params) -> object:
    """
    Выполняет один запрос к AnkiConnect и возвращает result.
    Бросает AnkiConnectError при любой ошибке.
    """
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise AnkiConnectError(
            f"Не удалось подключиться к AnkiConnect ({url}).\n"
            f"Убедитесь, что Anki запущен и аддон AnkiConnect установлен.\n"
            f"Причина: {exc}"
        ) from exc

    if body.get("error"):
        raise AnkiConnectError(f"AnkiConnect вернул ошибку [{action}]: {body['error']}")
    return body["result"]


def _ac_ensure_deck(url: str, deck_name: str) -> None:
    """Создаёт колоду, если её ещё нет."""
    _ankiconnect_request(url, "createDeck", deck=deck_name)


def _ac_ensure_model(url: str, model: genanki.Model) -> None:
    """
    Создаёт модель (тип карточек) в Anki, если её ещё нет.
    Если модель с таким именем уже есть — пропускает (не перезаписывает).
    """
    existing = _ankiconnect_request(url, "modelNames")
    if model.name in existing:
        return

    templates = [
        {
            "Name": t["name"],
            "Front": t["qfmt"],
            "Back":  t["afmt"],
        }
        for t in model.templates
    ]
    _ankiconnect_request(
        url, "createModel",
        modelName=model.name,
        inOrderFields=[f["name"] for f in model.fields],
        css=model.css,
        cardTemplates=templates,
    )


def _ac_store_media(url: str, filename: str, path: Path) -> None:
    """Загружает медиафайл в коллекцию Anki через AnkiConnect."""
    data = base64.b64encode(path.read_bytes()).decode()
    _ankiconnect_request(url, "storeMediaFile", filename=filename, data=data)


def _ac_add_notes(url: str, deck_name: str, model_name: str, notes_data: list[dict]) -> list[int]:
    """
    Добавляет заметки через addNotes (батчем).
    notes_data — список {"fields": {...}, "tags": [...]}
    Возвращает список ID добавленных заметок (None означает дубликат).
    """
    notes = [
        {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": n["fields"],
            "tags": n.get("tags", []),
            "options": {"allowDuplicate": False, "duplicateScope": "deck"},
        }
        for n in notes_data
    ]
    return _ankiconnect_request(url, "addNotes", notes=notes)


# ──────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────

CARD_CSS = """
/* ── Base ─────────────────────────────────── */
:root {
  --accent:          #e8a87c;
  --accent2:         #e67e22;
  --hl-word:         rgba(232,168,124,.22);
  --hl-word-border:  #e8a87c;
  --hl-gram:         rgba(230,126,34,.22);
  --hl-gram-border:  #e67e22;
  --card-bg:         #1e1e2e;
  --text:            #e0dfe8;
  --subtext:         #9e9bb0;
  --surface0:        #2a2a3d;
  --surface1:        #3c3a52;
  --green:           #a8d8a8;
  --yellow:          #f9e2af;
  --mauve:           #cba6f7;
}

html, body { margin: 0; padding: 0; }

.card {
  font-family: 'Noto Sans JP', 'Segoe UI', sans-serif;
  background: var(--card-bg);
  color: var(--text);
  min-height: 100vh;
  padding: 0;
  margin: 0;
  font-size: 16px;
}

/* ── Layout ───────────────────────────────── */
#card-root {
  max-width: 640px;
  margin: 0 auto;
  padding: 20px 16px 36px;
  box-sizing: border-box;
  text-align: center;
}

/* ── Sentence wrapper (для фуриганы над словами) ── */
#sentence-wrap {
  margin-bottom: 12px;
}

/* Режим inline-ruby: когда фуригана показывается над словами */
#sentence-block {
  font-size: 1.45em;
  line-height: 1.7;
  word-break: break-all;
  display: inline;
}

/* Режим ruby для фуриганы над предложением */
#sentence-block.furigana-mode {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: center;
  align-items: flex-end;
  gap: 0;
  line-height: 1;
}

.ruby-unit {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  line-height: 1;
  margin: 0 1px;
}

.ruby-unit .ruby-top {
  font-size: .52em;
  color: var(--yellow);
  line-height: 1.3;
  min-height: 1em;
  white-space: nowrap;
}

.ruby-unit .ruby-base {
  font-size: 1em;
  line-height: 1.6;
  white-space: nowrap;
}

/* Подсветка в режиме plain */
#sentence-block .hl-word,
#sentence-block .hl-gram {
  border-radius: 3px;
  cursor: pointer;
  padding: 1px 2px;
  transition: background .15s;
}

#sentence-block .hl-word {
  background: var(--hl-word);
  border-bottom: 2px solid var(--hl-word-border);
}
#sentence-block .hl-word:hover  { background: rgba(232,168,124,.42); }
#sentence-block .hl-word.active { background: rgba(232,168,124,.55); }

#sentence-block .hl-gram {
  background: var(--hl-gram);
  border-bottom: 2px solid var(--hl-gram-border);
}
#sentence-block .hl-gram:hover  { background: rgba(230,126,34,.42); }
#sentence-block .hl-gram.active { background: rgba(230,126,34,.55); }

/* Подсветка внутри ruby-unit */
.ruby-unit.hl-word {
  background: var(--hl-word);
  border-bottom: 2px solid var(--hl-word-border);
  border-radius: 3px;
  cursor: pointer;
  padding: 0 2px;
  transition: background .15s;
}
.ruby-unit.hl-word:hover  { background: rgba(232,168,124,.42); }
.ruby-unit.hl-word.active { background: rgba(232,168,124,.55); }

.ruby-unit.hl-gram {
  background: var(--hl-gram);
  border-bottom: 2px solid var(--hl-gram-border);
  border-radius: 3px;
  cursor: pointer;
  padding: 0 2px;
  transition: background .15s;
}
.ruby-unit.hl-gram:hover  { background: rgba(230,126,34,.42); }
.ruby-unit.hl-gram.active { background: rgba(230,126,34,.55); }

/* ── Audio ────────────────────────────────── */
.audio-wrap {
  margin: 6px 0 10px;
}

/* ── Translations ─────────────────────────── */
#literal-block {
  display: none;
  font-size: .88em;
  color: var(--subtext);
  margin: 4px 0 8px;
  font-style: italic;
}
#natural-block {
  font-size: 1.05em;
  margin-bottom: 16px;
}

/* ── Buttons ──────────────────────────────── */
.btn-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 14px;
}

.btn {
  padding: 7px 18px;
  border: 2px solid var(--surface1);
  border-radius: 20px;
  background: var(--surface0);
  color: var(--text);
  font-size: .9em;
  cursor: pointer;
  user-select: none;
  transition: all .15s;
}
.btn:hover { filter: brightness(1.15); }

.btn.active-transl { border-color: var(--accent);  color: var(--accent); }
.btn.active-gram   { border-color: var(--accent2); color: var(--accent2); }
.btn.active-more-1 { border-color: var(--green);   color: var(--green); }
.btn.active-more-2 { border-color: var(--mauve);   color: var(--mauve); }

/* ── Detail panel ─────────────────────────── */
#detail-panel {
  display: none;
  margin-top: 14px;
  padding: 14px 16px;
  background: var(--surface0);
  border-radius: 12px;
  font-size: .95em;
  text-align: left;
}

/* Фуригана в панели (слова) */
.detail-furigana {
  font-size: .76em;
  color: var(--yellow);
  margin-bottom: 3px;
}

/* name грамматики (moreLevel==2) */
.detail-name {
  font-size: .8em;
  color: var(--mauve);
  margin-bottom: 5px;
}

/* Строка: surface [+ category справа для грамматики] */
.detail-surface-row {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  font-size: 1.2em;
  font-weight: 600;
  margin-bottom: 5px;
}

/* Бейдж category — ПОСЛЕ surface */
.detail-category {
  font-size: .65em;
  color: var(--subtext);
  border: 1px solid var(--surface1);
  border-radius: 4px;
  padding: 1px 6px;
  font-weight: 400;
  align-self: center;
}

/* Строка: translation  [часть речи справа] */
.detail-trans-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 3px;
}

.detail-translation {
  font-size: 1em;
  flex: 1;
}

.detail-pos {
  font-size: .78em;
  color: var(--subtext);
  white-space: nowrap;
}

/* Лемма — стоит рядом с surface в одной строке.
   Сверху маленький лейбл «lemma», снизу само значение серым. */
.detail-lemma-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  margin-left: 14px;
  line-height: 1;
}

.detail-lemma-label {
  font-size: .55em;
  color: var(--subtext);
  opacity: .65;
  line-height: 1.4;
  letter-spacing: .03em;
}

.detail-lemma-val {
  font-size: .82em;
  font-weight: 600;
  color: var(--subtext);
  line-height: 1;
}

/* explanation — скрыто пока moreLevel==0 */
.detail-explanation {
  font-size: .88em;
  color: var(--subtext);
  margin: 6px 0 4px;
  border-left: 2px solid var(--surface1);
  padding-left: 8px;
  display: none;
}
.detail-explanation.visible {
  display: block;
}

.detail-role {
  font-size: .93em;
  margin-top: 5px;
}

/* ── Divider ──────────────────────────────── */
hr.sep {
  border: none;
  border-top: 1px solid var(--surface1);
  margin: 12px 0;
}
"""


# ──────────────────────────────────────────────
# JavaScript
# ──────────────────────────────────────────────

CARD_JS = r"""
(function(){
// ── Data ───────────────────────────────────
const WORDS  = JSON.parse(document.getElementById('data-words').textContent);
const GRAMS  = JSON.parse(document.getElementById('data-grams').textContent);

// ── State ───────────────────────────────────
let modeTransl = false;
let modeGram   = false;
let moreLevel  = 0; // 0=off, 1=on, 2=second

// ── Elements ────────────────────────────────
const sentBlock  = document.getElementById('sentence-block');
const litBlock   = document.getElementById('literal-block');
const detPanel   = document.getElementById('detail-panel');
const btnTransl  = document.getElementById('btn-transl');
const btnGram    = document.getElementById('btn-gram');
const btnMore    = document.getElementById('btn-more');

// ── Helpers ─────────────────────────────────

function cleanSurface(s){
  return s.replace(/\+/g,'').replace(/\s/g,'');
}

function escapeRegex(s){
  return s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
}

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

const rawSentence = sentBlock.getAttribute('data-raw');

// ── Сборка spans (позиции вхождений) ────────

function collectSpans(text, items, type){
  let spans = [];
  items.forEach((item, idx) => {
    const surface = cleanSurface(type === 'word' ? item.surface : item.surface);
    if(!surface) return;
    const rx = new RegExp(escapeRegex(surface), 'g');
    let m;
    while((m = rx.exec(text)) !== null){
      spans.push({start: m.index, end: m.index + surface.length, idx, type,
                  cls: type === 'word' ? 'hl-word' : 'hl-gram'});
    }
  });
  // сортировка, убираем перекрытия
  spans.sort((a,b) => a.start - b.start);
  let filtered = [], last = -1;
  spans.forEach(s => { if(s.start >= last){ filtered.push(s); last = s.end; } });
  return filtered;
}

// ── Режим plain (без фуриганы) ──────────────

function buildPlainHTML(spans){
  let result = '', pos = 0, text = rawSentence;
  spans.forEach(s => {
    if(s.start > pos) result += escapeHtml(text.slice(pos, s.start));
    result += `<span class="${s.cls}" data-idx="${s.idx}" data-type="${s.type}">`
            + escapeHtml(text.slice(s.start, s.end))
            + `</span>`;
    pos = s.end;
  });
  if(pos < text.length) result += escapeHtml(text.slice(pos));
  return result;
}

// ── Режим ruby (фуригана над словами) ───────
// Показывается когда modeTransl && moreLevel === 2

function buildRubyHTML(spans){
  // Строим карту: позиция → {furigana, span}
  // Если span === null — просто символ без разметки
  let result = '';
  let pos = 0, text = rawSentence;

  // Для span-ов ищем соответствующее слово из WORDS (только для hl-word)
  const furiganaMap = {};
  WORDS.forEach((w, i) => {
    if(w.furigana) furiganaMap[i] = w.furigana;
  });

  spans.forEach(s => {
    // Символы между span-ами — по одному ruby-unit без фуриганы
    if(s.start > pos){
      const chunk = text.slice(pos, s.start);
      // Разбиваем на отдельные символы, каждый — ruby-unit с пустым верхом
      for(const ch of chunk){
        result += `<span class="ruby-unit"><span class="ruby-top"></span>`
                + `<span class="ruby-base">${escapeHtml(ch)}</span></span>`;
      }
    }
    // Сам span
    const surface = text.slice(s.start, s.end);
    const furi    = (s.type === 'word' && furiganaMap[s.idx]) ? furiganaMap[s.idx] : '';
    const cls     = s.cls;
    result += `<span class="ruby-unit ${cls}" data-idx="${s.idx}" data-type="${s.type}">`
            + `<span class="ruby-top">${escapeHtml(furi)}</span>`
            + `<span class="ruby-base">${escapeHtml(surface)}</span>`
            + `</span>`;
    pos = s.end;
  });

  // Оставшиеся символы
  if(pos < text.length){
    for(const ch of text.slice(pos)){
      result += `<span class="ruby-unit"><span class="ruby-top"></span>`
              + `<span class="ruby-base">${escapeHtml(ch)}</span></span>`;
    }
  }
  return result;
}

// ── Основная перестройка предложения ────────

function buildSentenceHTML(){
  let spans = [];

  if(modeGram){
    spans = collectSpans(rawSentence, GRAMS, 'gram');
  } else if(modeTransl){
    spans = collectSpans(rawSentence, WORDS, 'word');
  }

  const useRuby = modeTransl && moreLevel === 2;

  if(useRuby){
    sentBlock.classList.add('furigana-mode');
    sentBlock.innerHTML = buildRubyHTML(spans);
  } else {
    sentBlock.classList.remove('furigana-mode');
    sentBlock.innerHTML = buildPlainHTML(spans);
  }

  attachClickHandlers();
}

function attachClickHandlers(){
  sentBlock.querySelectorAll('.hl-word,.hl-gram').forEach(el => {
    el.addEventListener('click', onSpanClick);
  });
}

function onSpanClick(e){
  const el = e.currentTarget;
  sentBlock.querySelectorAll('.hl-word,.hl-gram').forEach(x => x.classList.remove('active'));
  el.classList.add('active');
  const type = el.dataset.type;
  const idx  = parseInt(el.dataset.idx);
  if(type === 'word') showWordDetail(idx);
  if(type === 'gram') showGramDetail(idx);
}

// ── Word detail ──────────────────────────────
// Раскладка:
//   [фуригана]                       ← только moreLevel >= 1
//   surface  [lemma-wrap]            ← lemma рядом с surface, moreLevel === 2
//   translation          part_of_speech

function showWordDetail(idx){
  const w = WORDS[idx];
  let html = '';

  // Фуригана
  if(moreLevel >= 1 && w.furigana){
    html += `<div class="detail-furigana">${escapeHtml(w.furigana)}</div>`;
  }

  // Surface + lemma рядом (moreLevel==2)
  html += `<div class="detail-surface-row">`;
  html += `<span>${escapeHtml(w.surface)}</span>`;
  if(moreLevel === 2 && w.lemma){
    html += `<span class="detail-lemma-wrap">`
          + `<span class="detail-lemma-label">lemma</span>`
          + `<span class="detail-lemma-val">${escapeHtml(w.lemma)}</span>`
          + `</span>`;
  }
  html += `</div>`;

  // translation (слева) + part_of_speech (справа)
  html += `<div class="detail-trans-row">`;
  html += `<span class="detail-translation">${escapeHtml(w.translation || '')}</span>`;
  if(w.part_of_speech){
    html += `<span class="detail-pos">${escapeHtml(w.part_of_speech)}</span>`;
  }
  html += `</div>`;

  showDetail(html);
}

// ── Grammar detail ───────────────────────────
// Раскладка:
//   [name]                ← только moreLevel === 2
//   surface  [category]   ← category после surface, только moreLevel >= 1
//   [explanation]         ← только moreLevel >= 1
//   role_in_sentence

function showGramDetail(idx){
  const g = GRAMS[idx];
  let html = '';

  // name
  if(moreLevel === 2 && g.name){
    html += `<div class="detail-name">${escapeHtml(g.name)}</div>`;
  }

  // surface + category справа
  html += `<div class="detail-surface-row">`;
  html += `<span>${escapeHtml(cleanSurface(g.surface))}</span>`;
  if(moreLevel >= 1 && g.category){
    html += `<span class="detail-category">${escapeHtml(g.category)}</span>`;
  }
  html += `</div>`;

  // explanation — видна только при moreLevel >= 1
  const explVis = moreLevel >= 1 ? ' visible' : '';
  if(g.explanation){
    html += `<div class="detail-explanation${explVis}">${escapeHtml(g.explanation)}</div>`;
  }

  // role_in_sentence
  if(g.role_in_sentence){
    html += `<div class="detail-role">${escapeHtml(g.role_in_sentence)}</div>`;
  }

  showDetail(html);
}

function showDetail(html){
  detPanel.innerHTML = html;
  detPanel.style.display = 'block';
}

function hideDetail(){
  detPanel.style.display = 'none';
  detPanel.innerHTML = '';
  sentBlock.querySelectorAll('.hl-word,.hl-gram').forEach(x => x.classList.remove('active'));
}

// ── Button handlers ─────────────────────────

btnTransl.addEventListener('click', () => {
  modeTransl = !modeTransl;
  if(modeTransl) modeGram = false;
  btnTransl.className = 'btn' + (modeTransl ? ' active-transl' : '');
  btnGram.className   = 'btn' + (modeGram   ? ' active-gram'   : '');
  litBlock.style.display = modeTransl ? 'block' : 'none';
  hideDetail();
  buildSentenceHTML();
});

btnGram.addEventListener('click', () => {
  modeGram = !modeGram;
  if(modeGram) modeTransl = false;
  btnTransl.className = 'btn' + (modeTransl ? ' active-transl' : '');
  btnGram.className   = 'btn' + (modeGram   ? ' active-gram'   : '');
  litBlock.style.display = 'none';
  hideDetail();
  buildSentenceHTML();
});

btnMore.addEventListener('click', () => {
  // Сохраняем активный элемент ДО перестройки DOM
  const activeSpan = sentBlock.querySelector('.hl-word.active, .hl-gram.active');
  const activeType = activeSpan ? activeSpan.dataset.type : null;
  const activeIdx  = activeSpan ? parseInt(activeSpan.dataset.idx) : null;

  moreLevel = (moreLevel + 1) % 3;
  btnMore.className = ['btn','btn active-more-1','btn active-more-2'][moreLevel];

  // Перестраиваем предложение (фуригана появляется/исчезает)
  buildSentenceHTML();

  // Восстанавливаем active-класс на соответствующем элементе в новом DOM
  if(activeIdx !== null){
    const restored = sentBlock.querySelector(
      `[data-type="${activeType}"][data-idx="${activeIdx}"]`
    );
    if(restored) restored.classList.add('active');

    // Обновляем панель деталей
    if(activeType === 'word') showWordDetail(activeIdx);
    if(activeType === 'gram') showGramDetail(activeIdx);
  }
});

// ── Init ────────────────────────────────────
buildSentenceHTML();

})();
"""


# ──────────────────────────────────────────────
# Front template
# ──────────────────────────────────────────────

FRONT_TMPL = """
<div class="card">
  <div id="card-root">
    <div id="sentence-wrap">
      <div id="sentence-block" data-raw="{{sentence}}">{{sentence}}</div>
    </div>
    <div class="audio-wrap">{{audio}}</div>
  </div>
</div>
""".strip()


# ──────────────────────────────────────────────
# Back template
# ──────────────────────────────────────────────

BACK_TMPL = """
<div class="card">
  <div id="card-root">

    <!-- Скрытые данные -->
    <script id="data-words" type="application/json">{{words_json}}</script>
    <script id="data-grams"  type="application/json">{{grams_json}}</script>

    <!-- Предложение -->
    <div id="sentence-wrap">
      <div id="sentence-block" data-raw="{{sentence}}">{{sentence}}</div>
    </div>

    <!-- Аудио -->
    <div class="audio-wrap">{{audio}}</div>

    <!-- Буквальный перевод (скрыт до нажатия кнопки «Перевод») -->
    <div id="literal-block">{{literal_translation}}</div>

    <!-- Натуральный перевод -->
    <div id="natural-block">{{natural_translation}}</div>

    <!-- Кнопки -->
    <div class="btn-row">
      <button class="btn" id="btn-transl">Перевод</button>
      <button class="btn" id="btn-gram">Грамматика</button>
      <button class="btn" id="btn-more">Подробнее</button>
    </div>

    <hr class="sep">

    <!-- Панель деталей -->
    <div id="detail-panel"></div>

  </div>
</div>

<script>
""" + CARD_JS + """
</script>
""".strip()


# ──────────────────────────────────────────────
# Model builder
# ──────────────────────────────────────────────

def _build_model(model_name: str) -> genanki.Model:
    model_id = _stable_id(f"jp_sentence_model_{model_name}")
    return genanki.Model(
        model_id,
        model_name,
        fields=[
            {"name": "sentence"},
            {"name": "literal_translation"},
            {"name": "natural_translation"},
            {"name": "audio"},
            {"name": "words_json"},
            {"name": "grams_json"},
        ],
        templates=[
            {
                "name": "Card 1",
                "qfmt": FRONT_TMPL,
                "afmt": BACK_TMPL,
            }
        ],
        css=CARD_CSS,
    )


# ──────────────────────────────────────────────
# Main public function
# ──────────────────────────────────────────────

_DEFAULT_ANKICONNECT_URL = "http://127.0.0.1:8765"


def create_anki_deck(
    output_dir: Path,
    gpt_output_data: list[dict],
    *,
    ankiconnect: bool = False,
    ankiconnect_url: str = _DEFAULT_ANKICONNECT_URL,
) -> Path:
    """
    Создаёт .apkg файл с колодой Anki и опционально импортирует её через AnkiConnect.

    Parameters
    ----------
    output_dir : Path
        Директория проекта. Имя колоды = <последняя папка> + " sentences".
        Аудио ищется в output_dir / "sentences" / <sanitized_sentence>.mp3
    gpt_output_data : list[dict]
        Список словарей с полями sentence, literal_translation,
        natural_translation, words, grammar_points.
    ankiconnect : bool, optional
        Если True — дополнительно импортирует карточки в запущенный Anki
        через AnkiConnect. Anki должен быть открыт, аддон AnkiConnect установлен.
        По умолчанию False (только .apkg).
    ankiconnect_url : str, optional
        Адрес AnkiConnect. По умолчанию "http://127.0.0.1:8765".

    Returns
    -------
    Path
        Путь к созданному .apkg файлу.

    Raises
    ------
    AnkiConnectError
        Если ankiconnect=True и Anki недоступен или вернул ошибку.
    """
    output_dir = Path(output_dir)
    deck_name  = f"{output_dir.name} sentences"
    deck_id    = _stable_id(f"jp_deck_{deck_name}")
    model      = _build_model(deck_name)

    deck        = genanki.Deck(deck_id, deck_name)
    package     = genanki.Package(deck)
    media_files: list[str] = []

    # Данные для AnkiConnect (собираем параллельно)
    ac_notes:  list[dict] = []
    ac_media:  list[tuple[str, Path]] = []  # (filename, path)

    audio_dir = output_dir / "sentences"

    for item in gpt_output_data:
        sentence            = item.get("sentence", "")
        literal_translation = item.get("literal_translation", "")
        natural_translation = item.get("natural_translation", "")
        words               = item.get("words", [])
        grammar_points      = item.get("grammar_points", [])

        # ── Аудио ────────────────────────────
        safe_name   = sanitize_filename(sentence)
        mp3_name    = f"{safe_name}.mp3"
        audio_path  = audio_dir / mp3_name
        audio_field = ""

        if audio_path.exists():
            audio_field = f"[sound:{mp3_name}]"
            media_files.append(str(audio_path))
            ac_media.append((mp3_name, audio_path))
        else:
            print(f"[WARN] Audio not found: {audio_path}")

        # ── JSON для JS ───────────────────────
        words_json = json.dumps(words,          ensure_ascii=False)
        grams_json = json.dumps(grammar_points, ensure_ascii=False)

        fields = [
            sentence,
            literal_translation,
            natural_translation,
            audio_field,
            words_json,
            grams_json,
        ]
        field_names = [f["name"] for f in model.fields]

        note = genanki.Note(model=model, fields=fields)
        deck.add_note(note)

        ac_notes.append({
            "fields": dict(zip(field_names, fields)),
            "tags": [],
        })

    # ── Сохранение .apkg ─────────────────────
    package.media_files = media_files
    out_path = output_dir / f"{sanitize_filename(deck_name)}.apkg"
    package.write_to_file(str(out_path))
    print(f"[OK] .apkg saved: {out_path}  ({len(gpt_output_data)} notes)")

    # ── AnkiConnect импорт ────────────────────
    if ankiconnect:
        _import_via_ankiconnect(
            url=ankiconnect_url,
            deck_name=deck_name,
            model=model,
            ac_notes=ac_notes,
            ac_media=ac_media,
        )

    return out_path


def _import_via_ankiconnect(
    url: str,
    deck_name: str,
    model: genanki.Model,
    ac_notes: list[dict],
    ac_media: list[tuple[str, Path]],
) -> None:
    """Полный цикл импорта через AnkiConnect."""

    print(f"[AnkiConnect] Подключение к {url} ...")

    # 1. Проверка связи
    version = _ankiconnect_request(url, "version")
    print(f"[AnkiConnect] Версия API: {version}")

    # 2. Создать колоду (idempotent)
    _ac_ensure_deck(url, deck_name)
    print(f"[AnkiConnect] Колода готова: «{deck_name}»")

    # 3. Создать модель (idempotent)
    _ac_ensure_model(url, model)
    print(f"[AnkiConnect] Модель готова: «{model.name}»")

    # 4. Загрузить медиафайлы
    if ac_media:
        print(f"[AnkiConnect] Загрузка {len(ac_media)} аудиофайлов ...")
        for filename, path in ac_media:
            _ac_store_media(url, filename, path)
        print("[AnkiConnect] Аудио загружено.")

    # 5. Добавить заметки
    print(f"[AnkiConnect] Добавление {len(ac_notes)} карточек ...")
    results = _ac_add_notes(url, deck_name, model.name, ac_notes)

    added    = sum(1 for r in results if r is not None)
    skipped  = sum(1 for r in results if r is None)
    print(f"[AnkiConnect] Добавлено: {added}, пропущено (дубликаты): {skipped}")
    print("[AnkiConnect] Импорт завершён ✓")


# ──────────────────────────────────────────────
# Quick test / demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile, shutil, sys

    demo_data = [
        {
            "sentence": "未来から呼ばれたネコ型メイドロボ!",
            "literal_translation": "из будущего вызванный кото-тип горничная-робот!",
            "natural_translation": "Кошкообразный робот-горничная, вызванный из будущего!",
            "sentence_start": 3.446,
            "sentence_end": 5.42,
            "words": [
                {"surface": "未来",     "lemma": "未来",     "furigana": "みらい",   "translation": "будущее",               "part_of_speech": "noun"},
                {"surface": "呼ばれた", "lemma": "呼ぶ",     "furigana": "よばれた", "translation": "был вызван, был призван","part_of_speech": "verb"},
                {"surface": "ネコ型",   "lemma": "ネコ型",   "furigana": "ねこがた", "translation": "кошачьего типа",          "part_of_speech": "noun"},
                {"surface": "メイドロボ","lemma":"メイドロボ","furigana": "めいどろぼ","translation": "робот-горничная",        "part_of_speech": "noun"},
            ],
            "grammar_points": [
                {
                    "surface": "から",
                    "category": "particle",
                    "name": "Source marker から",
                    "explanation": "Указывает исходную точку.",
                    "role_in_sentence": "Показывает происхождение из будущего.",
                },
                {
                    "surface": "呼ばれた",
                    "category": "verb_conjugation",
                    "name": "Passive past",
                    "explanation": "Страдательная форма прошедшего времени.",
                    "role_in_sentence": "Описывает робота как вызванного кем-то.",
                },
            ],
        }
    ]

    # Флаг --ankiconnect запускает импорт через AnkiConnect
    use_ac = "--ankiconnect" in sys.argv

    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "doraemon"
        (project / "sentences").mkdir(parents=True)
        # Создаём фиктивный mp3 для теста
        safe = sanitize_filename("未来から呼ばれたネコ型メイドロボ!")
        (project / "sentences" / f"{safe}.mp3").write_bytes(b"\xff\xfb\x00" * 100)

        result = create_anki_deck(project, demo_data, ankiconnect=use_ac)
        dest = Path("demo_doraemon.apkg")
        shutil.copy(result, dest)
        print(f"Demo deck copied to: {dest.resolve()}")