from pathlib import Path
import base64
import json
import requests

ANKI_URL = "http://localhost:8765"


def cutter_str(s: str) -> str:
    return s[:4] + "-" + s[-4:] if len(s) > 8 else s


def anki(action: str, **params):
    response = requests.post(
        ANKI_URL,
        json={"action": action, "version": 6, "params": params},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("error"):
        raise RuntimeError(f"AnkiConnect error: {data['error']}")
    print("post action: " + action)
    return data["result"]


def upload_media(local_path: Path, target_filename: str) -> str | None:
    if not local_path.exists():
        return None
    with open(local_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    anki("storeMediaFile", filename=target_filename, data=encoded)
    return target_filename


def ensure_deck(deck_name: str):
    decks = anki("deckNames")
    if deck_name not in decks:
        anki("createDeck", deck=deck_name)


# ---------------------------------------------------------------------------
# HTML builder — только data-атрибуты, никакого UI внутри поля
# ---------------------------------------------------------------------------

def _escape(s: str) -> str:
    """Минимальный HTML-эскейп для значений атрибутов."""
    return (
        s.replace("&", "&amp;")
         .replace('"', "&quot;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
    )


def build_grammar_html(sentence: str, grammar_points: list[dict]) -> str:
    """
    Возвращает предложение, где каждый surface_form заменён на:
        <span class="gm" data-category="..." data-name="..."
              data-detail="..." data-role="...">слово</span>

    Весь попап/вкладки строятся JS-ом в шаблоне карточки —
    Anki не режет data-атрибуты на спанах.
    """
    if not grammar_points:
        return sentence

    # Длинные паттерны обрабатываем раньше коротких
    points = sorted(grammar_points, key=lambda p: len(p["surface_form"]), reverse=True)

    # Список сегментов: (is_html, text)
    segments: list[tuple[bool, str]] = [(False, sentence)]

    for point in points:
        surface = point["surface_form"]
        span = (
            f'<span class="gm"'
            f' data-category="{_escape(point.get("category", ""))}"'
            f' data-name="{_escape(point.get("grammar_name", ""))}"'
            f' data-detail="{_escape(point.get("detailed_explanation_ru", ""))}"'
            f' data-role="{_escape(point.get("role_in_sentence", ""))}"'
            f'>{surface}</span>'
        )

        new_segments: list[tuple[bool, str]] = []
        for is_html, text in segments:
            if is_html or surface not in text:
                new_segments.append((is_html, text))
                continue
            parts = text.split(surface)
            for i, part in enumerate(parts):
                if part:
                    new_segments.append((False, part))
                if i < len(parts) - 1:
                    new_segments.append((True, span))
        segments = new_segments

    return "".join(text for _, text in segments)


# ---------------------------------------------------------------------------
# Anki model
# ---------------------------------------------------------------------------

def ensure_model(model_name: str = "Japanese Song Vocabulary by tihun v3"):
    models = anki("modelNames")
    if model_name in models:
        return model_name

    # ------------------------------------------------------------------
    # CSS
    # ------------------------------------------------------------------
    css = r"""
* { box-sizing: border-box; }

html, body {
    margin: 0;
    padding: 0;
    overflow-x: hidden;   /* убираем горизонтальный скролл */
}

.card {
    font-family: "Noto Sans JP", sans-serif;
    text-align: center;
    padding: 12px 12px 20px;
    max-width: 600px;
    margin: 0 auto;
    width: 100%;
}

.word {
    font-size: clamp(28px, 7vw, 48px);
    font-weight: 600;
    margin: 8px 0;
    line-height: 1.2;
    word-break: keep-all;
}

ruby { font-size: clamp(20px, 5vw, 32px); }
ruby rt { font-size: 0.45em; color: #888; }

.translation {
    margin-top: 10px;
    font-size: clamp(15px, 4vw, 20px);
}

.image img {
    width: min(240px, 80vw);
    height: auto;
    border-radius: 8px;
    margin-top: 10px;
}

.sentence {
    margin-top: 14px;
    font-size: clamp(22px, 5.5vw, 30px);
    line-height: 2.2;
    position: relative;
    /* чтобы попапы не создавали горизонтальный скролл */
    overflow: visible;
}

.sentence-ru {
    margin-top: 6px;
    color: #888;
    font-size: clamp(13px, 3vw, 16px);
    line-height: 1.4;
}

/* ── Grammar highlights ── */
.gm {
    position: relative;
    display: inline-block;
    cursor: pointer;
    border-bottom: 2px solid currentColor;
    padding-bottom: 1px;
}

.gm[data-category="particle"]       { color: #e07b39; }
.gm[data-category="verb"]           { color: #3a9de0; }
.gm[data-category="verb conjugation"]{ color: #3a9de0; }
.gm[data-category="grammar pattern"]{ color: #8e44ad; }
.gm[data-category="noun"]           { color: #2ecc71; }

/* ── Popup (строится JS-ом, вставляется в .card) ── */
#gm-popup {
    display: none;
    position: fixed;       /* fixed — не зависит от скролла и не создаёт его */
    background: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 10px;
    width: min(280px, 88vw);
    text-align: left;
    font-size: 13px;
    line-height: 1.5;
    z-index: 9999;
    box-shadow: 0 4px 20px rgba(0,0,0,0.55);
    overflow: hidden;
}

#gm-popup.visible { display: block; }

/* Вкладки */
#gm-tabs {
    display: flex;
    background: #181825;
    border-bottom: 1px solid #45475a;
}

.gm-tab {
    flex: 1;
    padding: 6px 2px;
    font-size: 9px;
    color: #6c7086;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    font-family: inherit;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    transition: color .15s;
}
.gm-tab:hover { color: #cdd6f4; }
.gm-tab.active {
    color: #89b4fa;
    border-bottom-color: #89b4fa;
}

#gm-body {
    padding: 10px 12px;
    min-height: 44px;
    word-break: break-word;
}

/* Хвостик */
#gm-arrow {
    position: fixed;
    width: 0; height: 0;
    border: 7px solid transparent;
    z-index: 9998;
    pointer-events: none;
}
#gm-arrow.up   { border-bottom-color: #45475a; }
#gm-arrow.down { border-top-color:    #45475a; }
"""

    # ------------------------------------------------------------------
    # Front
    # ------------------------------------------------------------------
    front = r"""
<div class="word">{{surface}}{{audio_word}}</div>
"""

    # ------------------------------------------------------------------
    # Back — попап строится одним JS-блоком в шаблоне
    # ------------------------------------------------------------------
    back = r"""
{{FrontSide}}
<hr>

<div>
  <ruby>{{lemma}}<rt>{{furigana}}</rt></ruby>
</div>

<div class="translation">{{translation}}</div>

<div class="image">{{image}}</div>

<div class="sentence" id="gm-sentence">
  {{sentence_grammar}}{{audio_sentence}}
</div>

<div class="sentence-ru">{{sentence_ru}}</div>

<!-- Один попап на всю карточку -->
<div id="gm-popup">
  <div id="gm-tabs">
    <button class="gm-tab active" data-idx="0">Категория</button>
    <button class="gm-tab"        data-idx="1">Название</button>
    <button class="gm-tab"        data-idx="2">Объяснение</button>
    <button class="gm-tab"        data-idx="3">В предложении</button>
  </div>
  <div id="gm-body"></div>
</div>
<div id="gm-arrow"></div>

<script>
(function () {
  var popup  = document.getElementById('gm-popup');
  var body   = document.getElementById('gm-body');
  var arrow  = document.getElementById('gm-arrow');
  var tabs   = document.querySelectorAll('.gm-tab');
  var current = null;   // текущий активный .gm спан
  var activeTab = 0;

  var KEYS = ['category', 'name', 'detail', 'role'];

  /* ── Показать нужную вкладку ── */
  function renderTab(idx) {
    activeTab = idx;
    tabs.forEach(function (t) {
      t.classList.toggle('active', parseInt(t.dataset.idx) === idx);
    });
    body.textContent = (current && current.dataset[KEYS[idx]]) || '—';
  }

  /* ── Позиционировать попап у спана ── */
  function positionPopup(span) {
    var r   = span.getBoundingClientRect();
    var pw  = popup.offsetWidth;
    var ph  = popup.offsetHeight;
    var vw  = window.innerWidth;
    var vh  = window.innerHeight;
    var GAP = 10;

    // Горизонтально — центрируем под словом, не выходя за экран
    var left = r.left + r.width / 2 - pw / 2;
    left = Math.max(6, Math.min(left, vw - pw - 6));

    // Вертикально — пробуем сверху, иначе снизу
    var topAbove = r.top  - ph - GAP;
    var topBelow = r.bottom + GAP;
    var useAbove = topAbove >= 6;
    var top = useAbove ? topAbove : topBelow;

    popup.style.left = left + 'px';
    popup.style.top  = top  + 'px';

    // Хвостик
    var ax = r.left + r.width / 2 - 7;
    ax = Math.max(10, Math.min(ax, vw - 20));
    arrow.style.left = ax + 'px';
    if (useAbove) {
      arrow.style.top    = (r.top  - GAP + 3) + 'px';
      arrow.style.bottom = '';
      arrow.className = 'down';
    } else {
      arrow.style.top    = (r.bottom + GAP - 17) + 'px';
      arrow.style.bottom = '';
      arrow.className = 'up';
    }
  }

  /* ── Открыть попап ── */
  function openPopup(span) {
    current = span;
    renderTab(activeTab);
    popup.classList.add('visible');
    // Позиционируем после того как попап отрисован
    requestAnimationFrame(function () { positionPopup(span); });
  }

  /* ── Закрыть попап ── */
  function closePopup() {
    popup.classList.remove('visible');
    arrow.className = '';
    current = null;
  }

  /* ── Клики по спанам ── */
  document.querySelectorAll('.gm').forEach(function (span) {
    span.addEventListener('click', function (e) {
      e.stopPropagation();
      if (current === span) { closePopup(); return; }
      openPopup(span);
    });
  });

  /* ── Клики по вкладкам ── */
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function (e) {
      e.stopPropagation();
      renderTab(parseInt(tab.dataset.idx));
    });
  });

  /* ── Клик вне попапа — закрыть ── */
  document.addEventListener('click', function (e) {
    if (!popup.contains(e.target)) closePopup();
  });

  /* ── Десктоп hover — с таймером чтобы попап не пропадал при переходе на него ── */
  var hoverTimer = null;

  function cancelClose() {
    if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = null; }
  }

  function scheduleClose() {
    cancelClose();
    hoverTimer = setTimeout(closePopup, 120);
  }

  document.querySelectorAll('.gm').forEach(function (span) {
    span.addEventListener('mouseenter', function () {
      cancelClose();
      openPopup(span);
    });
    span.addEventListener('mouseleave', scheduleClose);
  });

  popup.addEventListener('mouseenter', cancelClose);
  popup.addEventListener('mouseleave', scheduleClose);

})();
</script>
"""

    anki(
        "createModel",
        modelName=model_name,
        inOrderFields=[
            "surface",
            "lemma",
            "furigana",
            "part_of_speech",
            "translation",
            "sentence",
            "sentence_grammar",
            "sentence_ru",
            "image",
            "audio_word",
            "audio_sentence",
        ],
        css=css,
        cardTemplates=[{"Name": "Vocabulary by tihun", "Front": front, "Back": back}],
    )

    return model_name


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

def import_to_anki(gpt_output_data: list[dict], output_dir: Path):
    deck_name   = output_dir.stem
    words_dir     = output_dir / "words"
    sentences_dir = output_dir / "sentences"
    images_dir    = output_dir / "images"

    print(f"Loaded {len(gpt_output_data)} cards")

    anki("version")
    ensure_deck(deck_name)
    model_name = ensure_model()

    song_name = output_dir.stem
    created = failed = 0

    for item in gpt_output_data:
        surface  = item.get("surface", item.get("word", ""))
        lemma    = item.get("lemma", surface)
        sentence = item.get("sentence", "")
        grammar_points = item.get("grammar_points", [])

        sentence_grammar_html = build_grammar_html(sentence, grammar_points)

        image_path          = images_dir    / f"{surface}.png"
        word_audio_path     = words_dir     / f"{surface}.mp3"
        sentence_audio_path = sentences_dir / f"{sentence}.mp3"

        cs = cutter_str(song_name)
        cw = cutter_str(surface)
        ce = cutter_str(sentence)

        image_file          = upload_media(image_path,          f"{cs}_{cw}.png")
        word_audio_file     = upload_media(word_audio_path,     f"{cs}_{cw}.mp3")
        sentence_audio_file = upload_media(sentence_audio_path, f"{cs}_{ce}.mp3")

        note = {
            "deckName":  deck_name,
            "modelName": model_name,
            "fields": {
                "surface":          surface,
                "lemma":            lemma,
                "furigana":         item.get("furigana", ""),
                "part_of_speech":   item.get("part_of_speech", ""),
                "translation":      item.get("translation", ""),
                "sentence":         sentence,
                "sentence_grammar": sentence_grammar_html,
                "sentence_ru":      item.get("sentence_ru", ""),
                "image":            f'<img src="{image_file}">'        if image_file          else "",
                "audio_word":       f"[sound:{word_audio_file}]"       if word_audio_file     else "",
                "audio_sentence":   f"[sound:{sentence_audio_file}]"   if sentence_audio_file else "",
            },
            "tags": ["song", song_name],
        }

        try:
            anki("addNote", note=note)
            created += 1
            print(f"[{created}] {surface}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {surface}: {e}")

    print(f"\nCreated: {created}")
    print(f"Failed : {failed}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python anki_import.py <anki.json> <output_dir>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    import_to_anki(data, Path(sys.argv[2]))