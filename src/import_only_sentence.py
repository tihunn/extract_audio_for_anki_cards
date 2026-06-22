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
  --accent: #4a90e2;
  --accent2: #e67e22;
  --accent3: #8e44ad;
  --hl-word: rgba(74,144,226,.25);
  --hl-gram: rgba(230,126,34,.25);
  --hl-word-border: #4a90e2;
  --hl-gram-border: #e67e22;
  --card-bg: #1e1e2e;
  --text: #cdd6f4;
  --subtext: #a6adc8;
  --surface0: #313244;
  --surface1: #45475a;
  --green:  #a6e3a1;
  --yellow: #f9e2af;
  --mauve:  #cba6f7;
  --red:    #f38ba8;
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
  padding: 16px 12px 32px;
  box-sizing: border-box;
}

/* ── Sentence ─────────────────────────────── */
#sentence-block {
  font-size: 1.45em;
  line-height: 1.7;
  margin-bottom: 10px;
  word-break: break-all;
}

#sentence-block .hl-word {
  background: var(--hl-word);
  border-bottom: 2px solid var(--hl-word-border);
  border-radius: 3px;
  cursor: pointer;
  padding: 1px 2px;
  transition: background .15s;
}
#sentence-block .hl-word:hover  { background: rgba(74,144,226,.45); }
#sentence-block .hl-word.active { background: rgba(74,144,226,.55); }

#sentence-block .hl-gram {
  background: var(--hl-gram);
  border-bottom: 2px solid var(--hl-gram-border);
  border-radius: 3px;
  cursor: pointer;
  padding: 1px 2px;
  transition: background .15s;
}
#sentence-block .hl-gram:hover  { background: rgba(230,126,34,.45); }
#sentence-block .hl-gram.active { background: rgba(230,126,34,.55); }

/* ── Translations ─────────────────────────── */
#literal-block {
  display: none;
  font-size: .9em;
  color: var(--subtext);
  margin: 4px 0 8px;
  font-style: italic;
}
#natural-block {
  font-size: 1.05em;
  margin-bottom: 14px;
}

/* ── Buttons ──────────────────────────────── */
.btn-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.btn {
  padding: 7px 16px;
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

/* Состояния кнопок */
.btn.active-transl { border-color: var(--accent); color: var(--accent); }
.btn.active-gram   { border-color: var(--accent2); color: var(--accent2); }
.btn.active-more-1 { border-color: var(--green);  color: var(--green); }
.btn.active-more-2 { border-color: var(--mauve);  color: var(--mauve); }

/* ── Detail panel ─────────────────────────── */
#detail-panel {
  display: none;
  margin-top: 14px;
  padding: 12px 14px;
  background: var(--surface0);
  border-radius: 10px;
  font-size: .95em;
}

.detail-furigana {
  font-size: .78em;
  color: var(--yellow);
  margin-bottom: 2px;
}

.detail-name {
  font-size: .82em;
  color: var(--mauve);
  margin-bottom: 4px;
}

.detail-surface-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 1.2em;
  font-weight: 600;
  margin-bottom: 4px;
}

.detail-category {
  font-size: .72em;
  color: var(--subtext);
  border: 1px solid var(--surface1);
  border-radius: 4px;
  padding: 1px 5px;
}

.detail-pos {
  font-size: .8em;
  color: var(--subtext);
  margin-top: 2px;
}

.detail-lemma {
  font-size: .8em;
  color: var(--subtext);
  font-style: italic;
  margin-right: 6px;
}

.detail-explanation {
  font-size: .9em;
  color: var(--subtext);
  margin: 5px 0;
  border-left: 2px solid var(--surface1);
  padding-left: 8px;
}

.detail-role {
  font-size: .92em;
  margin-top: 5px;
}

/* ── Divider ──────────────────────────────── */
hr.sep {
  border: none;
  border-top: 1px solid var(--surface1);
  margin: 10px 0;
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

// Исходный текст предложения (без разметки)
const rawSentence = sentBlock.getAttribute('data-raw');

function buildSentenceHTML(){
  let html = rawSentence;

  if(modeGram){
    // подсветка грамматических конструкций
    const markers = GRAMS.map(g => ({
      text: cleanSurface(g.surface),
      idx: GRAMS.indexOf(g),
      cls: 'hl-gram'
    })).filter(m => m.text && rawSentence.includes(m.text));

    html = applyHighlights(rawSentence, markers, 'gram');
  } else if(modeTransl){
    // подсветка слов
    const markers = WORDS.map((w,i) => ({
      text: cleanSurface(w.surface),
      idx: i,
      cls: 'hl-word'
    })).filter(m => m.text && rawSentence.includes(m.text));

    html = applyHighlights(rawSentence, markers, 'word');
  }

  sentBlock.innerHTML = html;
  attachClickHandlers();
}

function applyHighlights(text, markers, type){
  // Находим все совпадения с позициями
  let spans = [];
  markers.forEach(m => {
    const rx = new RegExp(escapeRegex(m.text),'g');
    let match;
    while((match = rx.exec(text)) !== null){
      spans.push({start: match.index, end: match.index + m.text.length, idx: m.idx, cls: m.cls, type});
    }
  });

  // Сортируем по началу, убираем перекрытия
  spans.sort((a,b) => a.start - b.start);
  let filtered = [], last = -1;
  spans.forEach(s => {
    if(s.start >= last){ filtered.push(s); last = s.end; }
  });

  // Строим HTML
  let result = '', pos = 0;
  filtered.forEach(s => {
    if(s.start > pos) result += escapeHtml(text.slice(pos, s.start));
    result += `<span class="${s.cls}" data-idx="${s.idx}" data-type="${s.type}">${escapeHtml(text.slice(s.start, s.end))}</span>`;
    pos = s.end;
  });
  if(pos < text.length) result += escapeHtml(text.slice(pos));
  return result;
}

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function attachClickHandlers(){
  sentBlock.querySelectorAll('.hl-word,.hl-gram').forEach(el => {
    el.addEventListener('click', onSpanClick);
  });
}

function onSpanClick(e){
  const el = e.currentTarget;
  const type = el.dataset.type;
  const idx  = parseInt(el.dataset.idx);

  // снимаем active со всех, ставим на текущий
  sentBlock.querySelectorAll('.hl-word,.hl-gram').forEach(x => x.classList.remove('active'));
  el.classList.add('active');

  if(type === 'word')  showWordDetail(idx);
  if(type === 'gram')  showGramDetail(idx);
}

function showWordDetail(idx){
  const w = WORDS[idx];
  let html = '';

  // Фуригана (только если moreLevel >= 1)
  if(moreLevel >= 1 && w.furigana){
    html += `<div class="detail-furigana">${escapeHtml(w.furigana)}</div>`;
  }

  // Surface + (lemma если moreLevel==2)
  html += `<div class="detail-surface-row">`;
  if(moreLevel === 2 && w.lemma){
    html += `<span class="detail-lemma">${escapeHtml(w.lemma)}</span>`;
  }
  html += `<span>${escapeHtml(w.surface)}</span>`;
  html += `</div>`;

  // part_of_speech + translation
  html += `<div class="detail-pos">`;
  html += `<span class="detail-pos">${escapeHtml(w.part_of_speech || '')}&nbsp;</span>`;
  html += `<span>${escapeHtml(w.translation || '')}</span>`;
  html += `</div>`;

  showDetail(html);
}

function showGramDetail(idx){
  const g = GRAMS[idx];
  let html = '';

  // name (если moreLevel==2)
  if(moreLevel === 2 && g.name){
    html += `<div class="detail-name">${escapeHtml(g.name)}</div>`;
  }

  // surface row + category
  html += `<div class="detail-surface-row">`;
  if(moreLevel >= 1 && g.category){
    html += `<span class="detail-category">${escapeHtml(g.category)}</span>`;
  }
  html += `<span>${escapeHtml(cleanSurface(g.surface))}</span>`;
  html += `</div>`;

  // explanation
  if(g.explanation){
    html += `<div class="detail-explanation">${escapeHtml(g.explanation)}</div>`;
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
  if(modeTransl){ modeGram = false; }

  btnTransl.className = 'btn' + (modeTransl ? ' active-transl' : '');
  btnGram.className   = 'btn' + (modeGram   ? ' active-gram'   : '');
  litBlock.style.display = modeTransl ? 'block' : 'none';
  hideDetail();
  buildSentenceHTML();
});

btnGram.addEventListener('click', () => {
  modeGram = !modeGram;
  if(modeGram){ modeTransl = false; }

  btnTransl.className = 'btn' + (modeTransl ? ' active-transl' : '');
  btnGram.className   = 'btn' + (modeGram   ? ' active-gram'   : '');
  litBlock.style.display = 'none';
  hideDetail();
  buildSentenceHTML();
});

btnMore.addEventListener('click', () => {
  moreLevel = (moreLevel + 1) % 3;

  const cls = ['btn','btn active-more-1','btn active-more-2'][moreLevel];
  btnMore.className = cls;

  // Если панель открыта — перерисовать
  if(detPanel.style.display === 'block'){
    const activeSpan = sentBlock.querySelector('.hl-word.active, .hl-gram.active');
    if(activeSpan){
      const type = activeSpan.dataset.type;
      const idx  = parseInt(activeSpan.dataset.idx);
      if(type === 'word') showWordDetail(idx);
      if(type === 'gram') showGramDetail(idx);
    }
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
    <div id="sentence-block" data-raw="{{sentence}}">{{sentence}}</div>
    {{audio}}
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
    <div id="sentence-block" data-raw="{{sentence}}">{{sentence}}</div>

    <!-- Буквальный перевод (скрыт до нажатия) -->
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