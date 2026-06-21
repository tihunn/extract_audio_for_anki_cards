# -*- coding: utf-8 -*-
"""
Модуль импорта предложений в Anki через AnkiConnect.

Главная функция: import_sentences_to_anki(output_dir, gpt_output_data)

Логика:
1. Имя колоды = "<имя последней папки output_dir> sentence"
2. Данные группируются по полю "sentence": идущие подряд записи с одинаковым
   sentence считаются словами одного предложения и собираются в одну карточку.
   Как только sentence меняется и потом снова встречается старое значение —
   это уже не учитывается (см. _group_words_into_sentences).
3. Для каждой группы слов создаётся одна заметка (note) в Anki:
   - Front: аудио предложения + сам текст sentence
   - Back:  тот же sentence + перевод предложения (sentence_ru) + кликабельные
            слова с переводом/грамматикой/фуриганой (через JS) + extra-поле
4. Аудио берётся из output_dir / "sentences" / <safe_filename(sentence)>.mp3
   и заливается в Anki через storeMediaFile.
5. Модель (Note Type) создаётся через createModel, если её ещё нет.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

ANKICONNECT_URL = "http://127.0.0.1:8765"
ANKICONNECT_VERSION = 6

MODEL_NAME = "Sentence Mining (JS)"


# --------------------------------------------------------------------------- #
# Низкоуровневый клиент AnkiConnect
# --------------------------------------------------------------------------- #

class AnkiConnectError(RuntimeError):
    """Ошибка, возвращённая самим AnkiConnect (поле 'error' в ответе)."""


def invoke(action: str, **params: Any) -> Any:
    """
    Отправляет один запрос к AnkiConnect и возвращает поле 'result'.
    Бросает AnkiConnectError, если AnkiConnect вернул ошибку,
    и ConnectionError, если Anki не запущен / AnkiConnect недоступен.
    """
    payload = json.dumps(
        {"action": action, "version": ANKICONNECT_VERSION, "params": params}
    ).encode("utf-8")

    request = urllib.request.Request(ANKICONNECT_URL, payload)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response_data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ConnectionError(
            "Не удалось подключиться к AnkiConnect. "
            "Убедитесь, что Anki запущен и плагин AnkiConnect установлен "
            f"({ANKICONNECT_URL})."
        ) from exc

    if len(response_data) != 2:
        raise AnkiConnectError("Неожиданный формат ответа AnkiConnect (лишние поля).")
    if "error" not in response_data:
        raise AnkiConnectError("Неожиданный формат ответа AnkiConnect (нет поля 'error').")
    if "result" not in response_data:
        raise AnkiConnectError("Неожиданный формат ответа AnkiConnect (нет поля 'result').")

    if response_data["error"] is not None:
        raise AnkiConnectError(str(response_data["error"]))

    return response_data["result"]


# --------------------------------------------------------------------------- #
# Очистка имени файла (должна совпадать с той, что использовалась при
# сохранении mp3-файлов на диске!)
# --------------------------------------------------------------------------- #

# Запрещённые в Windows символы: \ / : * ? " < > |
_WINDOWS_FORBIDDEN_CHARS = re.compile(r'[\\/:*?"<>|]')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename(name: str, max_length: int = 150) -> str:
    """
    Превращает произвольную строку в безопасное для Windows имя файла
    (без расширения). Должно соответствовать логике, которой создавались
    исходные .mp3 файлы.
    """
    cleaned = _WINDOWS_FORBIDDEN_CHARS.sub("", name)
    # Управляющие символы и завершающие точки/пробелы Windows тоже не любит
    cleaned = "".join(ch for ch in cleaned if ord(ch) >= 32)
    cleaned = cleaned.strip(" .")

    if not cleaned:
        cleaned = "untitled"

    if cleaned.upper() in _WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip(" .")

    return cleaned


# --------------------------------------------------------------------------- #
# Группировка слов в предложения
# --------------------------------------------------------------------------- #

def _group_words_into_sentences(gpt_output_data: list[dict]) -> list[list[dict]]:
    """
    Проходит по списку слов и группирует их в предложения.

    Правило: записи с одинаковым sentence идут подряд. Как только встречаем
    новое значение sentence — открываем новую группу. Если ранее встреченное
    значение sentence попадётся снова позже (не подряд) — оно уже не
    присоединяется к старой группе, а считается ошибкой данных и пропускается
    с фиксацией предупреждения (т.к. по условию задачи поиск повторов
    "лучше прекратить" после первого блока).
    """
    groups: list[list[dict]] = []
    seen_sentences: set[str] = set()

    current_sentence: str | None = None
    current_group: list[dict] = []

    for entry in gpt_output_data:
        sentence = entry.get("sentence", "")

        if sentence == current_sentence:
            current_group.append(entry)
            continue

        # Sentence сменился — закрываем предыдущую группу (если была)
        if current_group:
            groups.append(current_group)

        if sentence in seen_sentences:
            # Это предложение уже было обработано раньше и закрыто.
            # По условию задачи повторный (не последовательный) блок
            # с тем же sentence игнорируется.
            print(
                f"[anki_import] Предупреждение: предложение повторно "
                f"встретилось не подряд и будет пропущено: {sentence!r}"
            )
            current_sentence = sentence
            current_group = []  # "мусорная" группа, не добавляем в groups
            continue

        seen_sentences.add(sentence)
        current_sentence = sentence
        current_group = [entry]

    # Добавляем последнюю незакрытую группу (если она "живая", т.е. не была
    # помечена как дубликат и обнулена выше)
    if current_group:
        groups.append(current_group)

    return groups


# --------------------------------------------------------------------------- #
# Подготовка медиа (аудио)
# --------------------------------------------------------------------------- #

def _audio_filename_for_sentence(sentence: str) -> str:
    return f"{safe_filename(sentence)}.mp3"


def _store_sentence_audio(sentence_dir: Path, sentence: str, deck_tag: str) -> str | None:
    """
    Заливает mp3-файл предложения в коллекцию Anki через storeMediaFile.
    Возвращает имя файла, под которым он сохранён в Anki (для использования
    в поле [sound:имя_файла.mp3]), либо None, если файл не найден.
    """
    audio_path = sentence_dir / _audio_filename_for_sentence(sentence)

    if not audio_path.exists():
        print(f"[anki_import] Предупреждение: аудио не найдено: {audio_path}")
        return None

    audio_bytes = audio_path.read_bytes()
    b64_data = base64.b64encode(audio_bytes).decode("ascii")

    # Префиксуем имя файла тегом колоды, чтобы избежать коллизий имён между
    # разными проектами/колодами в общем медиа-хранилище Anki.
    stored_name = f"{deck_tag}__{audio_path.name}"

    invoke("storeMediaFile", filename=stored_name, data=b64_data)
    return stored_name


# --------------------------------------------------------------------------- #
# Шаблон карточки: HTML / CSS / JS
# --------------------------------------------------------------------------- #

CARD_CSS = r"""
.card {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, "Noto Sans", sans-serif;
  font-size: 20px;
  line-height: 1.6;
  text-align: center;
  color: #1f2328;
  background-color: #ffffff;
  padding: 16px;
  max-width: 720px;
  margin: 0 auto;
  box-sizing: border-box;
}

/* Японский текст получает отдельный шрифтовый стек. Кириллица и латиница
   НЕ должны попадать сюда — у CJK-шрифтов (Noto Sans JP/Hiragino/Yu Gothic)
   нет нормальных кириллических глифов, и браузер расставляет кириллицу
   по широкой "иероглифической" сетке (отсюда разреженный интервал между
   русскими буквами). Поэтому общий .card использует обычный текстовый
   стек, а .jp применяется только к элементам с японским текстом. */
.jp {
  font-family: "Hiragino Sans", "Yu Gothic", "Noto Sans JP", "Noto Sans",
    sans-serif;
}

.sentence-block {
  font-size: 30px;
  line-height: 1.9;
  margin-bottom: 18px;
  word-break: break-word;
  text-align: center;
}

.sentence-block .word {
  cursor: pointer;
  border-radius: 4px;
  padding: 0 1px;
  transition: background-color 0.15s ease;
}

.sentence-block .word:hover,
.sentence-block .word.active {
  background-color: #fff1a8;
}

/* Каждый символ предложения обёрнут в .ch — это даёт точную, посимвольную
   подсветку грамматики (surface_form), не зависящую от разбивки на .word */
.sentence-block .ch {
  transition: background-color 0.15s ease;
  border-radius: 2px;
}

.sentence-block .ch.grammar-highlight {
  background-color: #b9e6ff;
}

.translation-block {
  display: none;
  font-size: 20px;
  color: #444b52;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e3e6ea;
}

.translation-block.visible {
  display: block;
}

.translation-block .label,
.extra-block .label {
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #8a9099;
  margin-bottom: 4px;
}

/* ---- Панель информации о слове (появляется по клику/наведению) ---- */

.word-info {
  display: none;
  border: 1px solid #e3e6ea;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 16px;
  background: #f8f9fb;
  box-sizing: border-box;
  text-align: left;
}

.word-info.visible {
  display: block;
}

.word-info-surface {
  font-size: 26px;
  font-weight: 600;
  margin-bottom: 2px;
}

.word-info-furigana {
  font-size: 14px;
  color: #8a9099;
  margin-bottom: 8px;
  display: none;
}

.word-info-furigana.visible {
  display: block;
}

.word-info-translation {
  display: none;
  font-size: 19px;
  color: #1f2328;
  margin-bottom: 4px;
}

.word-info-translation.visible {
  display: block;
}

.word-info-pos {
  display: none;
  font-size: 13px;
  color: #8a9099;
  margin-bottom: 10px;
}

.word-info-pos.visible {
  display: block;
}

/* ---- Грамматика: отдельный, более крупный блок ---- */

.grammar-section {
  display: none;
  border: 1px solid #d8e6ff;
  border-radius: 10px;
  padding: 14px 16px;
  margin-top: 10px;
  background: #f3f8ff;
  box-sizing: border-box;
  text-align: left;
}

.grammar-section.visible {
  display: block;
}

.grammar-tabs {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 6px;
  margin-bottom: 10px;
}

.grammar-tab {
  font-size: 13px;
  padding: 5px 10px;
  border-radius: 999px;
  background: #e6eefc;
  color: #2952a3;
  cursor: pointer;
  border: 1px solid transparent;
  white-space: nowrap;
}

.grammar-tab.active {
  background: #2952a3;
  color: #ffffff;
}

.grammar-entry {
  display: none;
}

.grammar-entry.active {
  display: block;
}

.grammar-name {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 2px;
}

.grammar-category {
  font-size: 12px;
  color: #5b6573;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 8px;
}

.grammar-explanation,
.grammar-role {
  font-size: 16px;
  line-height: 1.55;
  margin-bottom: 6px;
  word-break: break-word;
}

.grammar-role {
  color: #444b52;
}

/* ---- Переключатели полей ---- */

.toggle-bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin-bottom: 16px;
}

.toggle-btn {
  font-size: 13px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid #d0d4d9;
  background: #ffffff;
  color: #444b52;
  cursor: pointer;
}

.toggle-btn.active {
  background: #1f2328;
  color: #ffffff;
  border-color: #1f2328;
}

.extra-block {
  font-size: 15px;
  color: #444b52;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid #e3e6ea;
  white-space: pre-wrap;
  word-break: break-word;
  text-align: left;
}

/* ---- Адаптация под телефон ---- */

@media (max-width: 480px) {
  .card {
    font-size: 17px;
    padding: 10px;
  }
  .sentence-block {
    font-size: 24px;
    line-height: 1.8;
  }
  .word-info-surface {
    font-size: 22px;
  }
  .grammar-name {
    font-size: 16px;
  }
  .grammar-explanation,
  .grammar-role {
    font-size: 15px;
  }
  .toggle-btn {
    font-size: 12px;
    padding: 5px 10px;
  }
}
"""

# Front: только аудио + сам текст предложения (без интерактива)
FRONT_TEMPLATE = r"""
<div class="sentence-block">{{Sentence}}</div>
<div>{{Audio}}</div>
"""

# Back: интерактивное предложение + перевод + панель слова/грамматики + extra
BACK_TEMPLATE = r"""
<div class="sentence-block jp" id="sentence-block">{{Sentence}}</div>
<div>{{Audio}}</div>

<div class="toggle-bar">
  <div class="toggle-btn" id="toggle-translation">Перевод</div>
  <div class="toggle-btn" id="toggle-furigana">Фуригана</div>
  <div class="toggle-btn" id="toggle-grammar">Грамматика</div>
</div>

<div class="translation-block" id="translation-block">
  <div class="label">Перевод предложения</div>
  <div id="sentence-translation">{{SentenceTranslation}}</div>
</div>

<div class="word-info" id="word-info">
  <div class="word-info-surface jp" id="word-info-surface"></div>
  <div class="word-info-furigana jp" id="word-info-furigana"></div>
  <div class="word-info-translation" id="word-info-translation"></div>
  <div class="word-info-pos" id="word-info-pos"></div>
</div>

<div class="grammar-section" id="grammar-section">
  <div class="grammar-tabs jp" id="grammar-tabs"></div>
  <div id="grammar-entries"></div>
</div>

<div class="extra-block">{{Extra}}</div>

<div id="words-data" style="display:none">{{WordsData}}</div>

<script>
(function () {
  var dataEl = document.getElementById("words-data");
  var words = [];
  try {
    words = JSON.parse(dataEl.textContent || dataEl.innerText || "[]");
  } catch (e) {
    words = [];
  }

  var sentenceBlock = document.getElementById("sentence-block");
  var rawSentenceText = sentenceBlock.textContent; // исходный текст, без разметки

  var translationBlock = document.getElementById("translation-block");
  var wordInfo = document.getElementById("word-info");
  var wordInfoSurface = document.getElementById("word-info-surface");
  var wordInfoFurigana = document.getElementById("word-info-furigana");
  var wordInfoTranslation = document.getElementById("word-info-translation");
  var wordInfoPos = document.getElementById("word-info-pos");

  var grammarSection = document.getElementById("grammar-section");
  var grammarTabs = document.getElementById("grammar-tabs");
  var grammarEntries = document.getElementById("grammar-entries");

  var toggleTranslation = document.getElementById("toggle-translation");
  var toggleFurigana = document.getElementById("toggle-furigana");
  var toggleGrammar = document.getElementById("toggle-grammar");

  // Перевод включён по умолчанию (приоритетная информация), фуригана и
  // грамматика - по запросу. Грамматике нужно много места, поэтому она
  // взаимоисключающая с переводом/фуриганой: включение грамматики гасит
  // оба остальных переключателя, и наоборот.
  var showTranslation = true;
  var showFurigana = false;
  var showGrammar = false;

  // -------- собираем кликабельные слова в предложении --------
  function buildSentenceHTML() {
    var sentenceText = rawSentenceText;
    var html = "";

    // последовательная разметка: ищем surface каждого слова по порядку,
    // начиная с того места, где остановились в прошлый раз
    var searchFrom = 0;
    var spans = [];
    words.forEach(function (w, idx) {
      if (!w.surface) return;
      var pos = sentenceText.indexOf(w.surface, searchFrom);
      if (pos === -1) {
        pos = sentenceText.indexOf(w.surface, 0);
      }
      if (pos === -1) return;
      spans.push({ start: pos, end: pos + w.surface.length, idx: idx });
      searchFrom = pos + w.surface.length;
    });

    spans.sort(function (a, b) { return a.start - b.start; });

    var lastEnd = 0;
    spans.forEach(function (sp) {
      if (sp.start < lastEnd) return; // пропускаем пересечения
      html += wrapChars(sentenceText.slice(lastEnd, sp.start));
      html += '<span class="word" data-idx="' + sp.idx + '">' +
        wrapChars(sentenceText.slice(sp.start, sp.end)) +
        "</span>";
      lastEnd = sp.end;
    });
    html += wrapChars(sentenceText.slice(lastEnd));

    sentenceBlock.innerHTML = html || escapeHtml(sentenceText);
  }

  // Оборачивает каждый символ диапазона в <span class="ch" data-pos="N">,
  // где N - абсолютная позиция символа в rawSentenceText. Это даёт
  // возможность подсвечивать грамматику по точному диапазону символов,
  // а не по совпадению с целыми .word-токенами (которых может не быть
  // для отдельных частиц вроде "が").
  function wrapChars(str) {
    var out = "";
    for (var i = 0; i < str.length; i++) {
      var ch = str[i];
      out += '<span class="ch" data-pos="' + currentPos + '">' + escapeHtml(ch) + "</span>";
      currentPos++;
    }
    return out;
  }

  var currentPos = 0;

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // -------- показ информации о слове --------
  function clearWordHighlights() {
    var els = sentenceBlock.querySelectorAll(".word.active");
    els.forEach(function (el) {
      el.classList.remove("active");
    });
  }

  function clearGrammarHighlights() {
    var els = sentenceBlock.querySelectorAll(".ch.grammar-highlight");
    els.forEach(function (el) {
      el.classList.remove("grammar-highlight");
    });
  }

  function showWordInfo(idx, el) {
    var w = words[idx];
    if (!w) return;

    clearWordHighlights();
    if (el) el.classList.add("active");

    wordInfoSurface.textContent = w.surface || "";
    wordInfoTranslation.textContent = w.translation || "";
    wordInfoPos.textContent = w.part_of_speech || "";
    wordInfoFurigana.textContent = w.furigana || "";

    wordInfo.classList.add("visible");
    applyVisibilityState();

    renderGrammar(w);
  }

  // -------- грамматика --------
  function renderGrammar(w) {
    grammarTabs.innerHTML = "";
    grammarEntries.innerHTML = "";

    var points = (w && w.grammar_points) || [];

    if (!showGrammar || points.length === 0) {
      grammarSection.classList.remove("visible");
      clearGrammarHighlights();
      return;
    }

    grammarSection.classList.add("visible");

    points.forEach(function (gp, i) {
      var tab = document.createElement("div");
      tab.className = "grammar-tab" + (i === 0 ? " active" : "");
      // Название пункта берётся из surface_form (как попросил пользователь),
      // с fallback на grammar_name на случай отсутствия surface_form.
      tab.textContent = gp.surface_form || gp.grammar_name || ("Вариант " + (i + 1));
      tab.setAttribute("data-gidx", i);
      grammarTabs.appendChild(tab);

      var entry = document.createElement("div");
      entry.className = "grammar-entry" + (i === 0 ? " active" : "");
      entry.setAttribute("data-gidx", i);

      var nameEl = document.createElement("div");
      nameEl.className = "grammar-name";
      nameEl.textContent = gp.grammar_name || "";
      entry.appendChild(nameEl);

      var catEl = document.createElement("div");
      catEl.className = "grammar-category";
      catEl.textContent = gp.category || "";
      entry.appendChild(catEl);

      var explEl = document.createElement("div");
      explEl.className = "grammar-explanation";
      explEl.textContent = gp.detailed_explanation_ru || "";
      entry.appendChild(explEl);

      var roleEl = document.createElement("div");
      roleEl.className = "grammar-role";
      roleEl.textContent = gp.role_in_sentence || "";
      entry.appendChild(roleEl);

      grammarEntries.appendChild(entry);
    });

    highlightGrammarSurface(points[0]);
  }

  // Подсвечивает surface_form грамматики, находя его как точную подстроку
  // символов в исходном тексте предложения (rawSentenceText), а не через
  // сопоставление с .word-токенами. Это работает даже если surface_form
  // - это частица или фрагмент, для которого нет отдельного элемента в
  // массиве words (например "が" внутри "性格が..."), и не путает частично
  // совпадающие токены (например "せいで" больше не подсвечивает только
  // "せい" из соседнего токена).
  function highlightGrammarSurface(gp) {
    clearGrammarHighlights();
    if (!gp || !gp.surface_form) return;

    var needle = gp.surface_form;
    var pos = rawSentenceText.indexOf(needle);
    if (pos === -1) return;

    for (var i = pos; i < pos + needle.length; i++) {
      var charEl = sentenceBlock.querySelector('.ch[data-pos="' + i + '"]');
      if (charEl) charEl.classList.add("grammar-highlight");
    }
  }

  // -------- видимость блоков перевода/фуриганы/грамматики --------
  function applyVisibilityState() {
    translationBlock.classList.toggle("visible", showTranslation);
    wordInfoTranslation.classList.toggle("visible", showTranslation);
    wordInfoPos.classList.toggle("visible", showTranslation);

    var hasFurigana = wordInfoFurigana.textContent.trim().length > 0;
    wordInfoFurigana.classList.toggle("visible", showFurigana && hasFurigana);
  }

  function setExclusiveState(target) {
    // target: "translation" | "furigana" | "grammar"
    if (target === "grammar") {
      showGrammar = !showGrammar;
      if (showGrammar) {
        showTranslation = false;
        showFurigana = false;
      }
    } else if (target === "translation") {
      showTranslation = !showTranslation;
      if (showTranslation) showGrammar = false;
    } else if (target === "furigana") {
      showFurigana = !showFurigana;
      if (showFurigana) showGrammar = false;
    }

    toggleTranslation.classList.toggle("active", showTranslation);
    toggleFurigana.classList.toggle("active", showFurigana);
    toggleGrammar.classList.toggle("active", showGrammar);

    applyVisibilityState();

    var activeWordEl = sentenceBlock.querySelector(".word.active");
    var w = activeWordEl ? words[parseInt(activeWordEl.getAttribute("data-idx"), 10)] : null;
    renderGrammar(w);
  }

  // -------- обработчики --------
  sentenceBlock.addEventListener("click", function (e) {
    var target = e.target.closest(".word");
    if (!target) return;
    var idx = parseInt(target.getAttribute("data-idx"), 10);
    showWordInfo(idx, target);
  });

  sentenceBlock.addEventListener("mouseover", function (e) {
    var target = e.target.closest(".word");
    if (!target) return;
    var idx = parseInt(target.getAttribute("data-idx"), 10);
    showWordInfo(idx, target);
  });

  grammarTabs.addEventListener("click", function (e) {
    var tab = e.target.closest(".grammar-tab");
    if (!tab) return;
    var gidx = tab.getAttribute("data-gidx");

    grammarTabs.querySelectorAll(".grammar-tab").forEach(function (t) {
      t.classList.toggle("active", t === tab);
    });
    grammarEntries.querySelectorAll(".grammar-entry").forEach(function (en) {
      en.classList.toggle("active", en.getAttribute("data-gidx") === gidx);
    });

    var activeWordEl = sentenceBlock.querySelector(".word.active");
    var w = activeWordEl ? words[parseInt(activeWordEl.getAttribute("data-idx"), 10)] : null;
    if (w && w.grammar_points) {
      highlightGrammarSurface(w.grammar_points[parseInt(gidx, 10)]);
    }
  });

  // также подсвечиваем при наведении на таб грамматики, не только при клике
  grammarTabs.addEventListener("mouseover", function (e) {
    var tab = e.target.closest(".grammar-tab");
    if (!tab) return;
    var gidx = parseInt(tab.getAttribute("data-gidx"), 10);
    var activeWordEl = sentenceBlock.querySelector(".word.active");
    var w = activeWordEl ? words[parseInt(activeWordEl.getAttribute("data-idx"), 10)] : null;
    if (w && w.grammar_points && w.grammar_points[gidx]) {
      highlightGrammarSurface(w.grammar_points[gidx]);
    }
  });

  toggleTranslation.addEventListener("click", function () {
    setExclusiveState("translation");
  });

  toggleFurigana.addEventListener("click", function () {
    setExclusiveState("furigana");
  });

  toggleGrammar.addEventListener("click", function () {
    setExclusiveState("grammar");
  });

  buildSentenceHTML();
  toggleTranslation.classList.add("active"); // перевод включён по умолчанию
  applyVisibilityState();
})();
</script>
"""


# --------------------------------------------------------------------------- #
# Создание модели (Note Type), если её ещё нет
# --------------------------------------------------------------------------- #

MODEL_FIELDS = [
    "Sentence",            # текст предложения (используется и Front, и Back)
    "Audio",               # [sound:...] аудио предложения
    "SentenceTranslation", # перевод предложения (sentence_ru)
    "Extra",               # дополнительная информация
    "WordsData",           # JSON со словами предложения (для JS), скрытое поле
]


def _ensure_model_exists() -> None:
    """Создаёт note type в Anki, если он ещё не существует."""
    existing_models = invoke("modelNames")
    if MODEL_NAME in existing_models:
        return

    invoke(
        "createModel",
        modelName=MODEL_NAME,
        inOrderFields=MODEL_FIELDS,
        css=CARD_CSS,
        cardTemplates=[
            {
                "Name": "Sentence Card",
                "Front": FRONT_TEMPLATE,
                "Back": BACK_TEMPLATE,
            }
        ],
    )


# --------------------------------------------------------------------------- #
# Создание колоды
# --------------------------------------------------------------------------- #

def _ensure_deck_exists(deck_name: str) -> None:
    invoke("createDeck", deck=deck_name)


# --------------------------------------------------------------------------- #
# Сборка одной заметки из группы слов одного предложения
# --------------------------------------------------------------------------- #

def _build_note_fields(
    word_group: list[dict],
    output_dir: Path,
    deck_tag: str,
) -> dict[str, str] | None:
    sentence = word_group[0].get("sentence", "")
    if not sentence:
        return None

    sentence_translation = ""
    for w in word_group:
        if w.get("sentence_ru"):
            sentence_translation = w["sentence_ru"]
            break

    sentence_dir = output_dir / "sentences"
    stored_audio_name = _store_sentence_audio(sentence_dir, sentence, deck_tag)
    audio_field = f"[sound:{stored_audio_name}]" if stored_audio_name else ""

    words_payload = []
    for w in word_group:
        words_payload.append(
            {
                "surface": w.get("surface", ""),
                "lemma": w.get("lemma", ""),
                "furigana": w.get("furigana", ""),
                "part_of_speech": w.get("part_of_speech", ""),
                "translation": w.get("translation", ""),
                "grammar_points": w.get("grammar_points", []) or [],
            }
        )

    words_json = json.dumps(words_payload, ensure_ascii=False)
    # Экранируем </script> на случай, если в JSON встретится такая подстрока
    words_json_safe = words_json.replace("</", "<\\/")

    return {
        "Sentence": sentence,
        "Audio": audio_field,
        "SentenceTranslation": sentence_translation,
        "Extra": "",  # дополнительная информация: см. примечание ниже
        "WordsData": words_json_safe,
    }


# --------------------------------------------------------------------------- #
# Главная публичная функция
# --------------------------------------------------------------------------- #

def import_sentences_to_anki(output_dir: Path, gpt_output_data: list[dict]) -> dict:
    """
    Импортирует предложения из gpt_output_data в Anki через AnkiConnect.

    Параметры
    ---------
    output_dir : Path
        Папка проекта. Имя последней папки используется как часть имени
        колоды ("<имя_папки> sentence"). Аудио ожидается в
        output_dir / "sentences" / "<safe_filename(sentence)>.mp3".
    gpt_output_data : list[dict]
        Список слов (см. формат в примере), где подряд идущие записи с
        одинаковым полем "sentence" относятся к одному предложению.

    Возвращает
    ----------
    dict со статистикой: {"deck_name": str, "added": int, "skipped": int,
    "skipped_sentences": list[str], "note_ids": list[int]}.
    Поле "skipped_sentences" перечисляет тексты предложений, которые не
    попали в колоду — либо из-за ошибки данных (не подряд идущий повтор
    sentence), либо потому что Anki счёл заметку дублем уже существующей
    в колоде (по полю Sentence). Если важных предложений тут не должно
    быть — это и есть причина "пропажи" элементов.
    """
    output_dir = Path(output_dir)
    deck_tag = output_dir.name
    deck_name = f"{deck_tag} sentence"

    _ensure_model_exists()
    _ensure_deck_exists(deck_name)

    sentence_groups = _group_words_into_sentences(gpt_output_data)

    notes_to_add = []
    note_sentences = []  # параллельный список текстов предложений для диагностики
    skipped_sentences = []  # предложения, для которых не удалось построить fields

    for group in sentence_groups:
        fields = _build_note_fields(group, output_dir, deck_tag)
        if fields is None:
            skipped_sentences.append(group[0].get("sentence", "<пусто>"))
            continue

        notes_to_add.append(
            {
                "deckName": deck_name,
                "modelName": MODEL_NAME,
                "fields": fields,
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck",
                },
                "tags": [deck_tag],
            }
        )
        note_sentences.append(fields["Sentence"])

    if not notes_to_add:
        return {
            "deck_name": deck_name,
            "added": 0,
            "skipped": len(skipped_sentences),
            "skipped_sentences": skipped_sentences,
            "note_ids": [],
        }

    result_ids = invoke("addNotes", notes=notes_to_add)

    added = sum(1 for nid in result_ids if nid is not None)
    # Заметки, которые AnkiConnect не добавил — почти всегда потому что Anki
    # счёл их дублями уже существующей заметки (тот же текст в поле Sentence
    # внутри этой же колоды). addNotes тихо возвращает null в этом случае,
    # без явной ошибки — именно так "пропадают" предложения, если два разных
    # элемента gpt_output_data дали одинаковый текст Sentence, либо скрипт
    # запускался повторно по тем же данным.
    duplicate_sentences = [
        note_sentences[i] for i, nid in enumerate(result_ids) if nid is None
    ]
    skipped_sentences.extend(duplicate_sentences)
    failed = len(duplicate_sentences)

    if failed:
        print(
            f"[anki_import] Предупреждение: {failed} заметок не были добавлены "
            f"(Anki считает их дублями уже существующих в колоде '{deck_name}' "
            f"по полю Sentence): {duplicate_sentences}"
        )

    return {
        "deck_name": deck_name,
        "added": added,
        "skipped": len(skipped_sentences),
        "skipped_sentences": skipped_sentences,
        "note_ids": [nid for nid in result_ids if nid is not None],
    }


# --------------------------------------------------------------------------- #
# Пример запуска как самостоятельного скрипта
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    example_data = [
        {
            "surface": "少子高齢化",
            "lemma": "少子高齢化",
            "sentence": "少子高齢化を阻止するため、",
            "word_start": 1.74,
            "word_end": 2.76,
            "sentence_start": 1.788,
            "sentence_end": 3.446,
            "furigana": "しょうしこうれいか",
            "part_of_speech": "noun",
            "translation": "снижение рождаемости и старение населения",
            "sentence_ru": "Чтобы остановить сокращение рождаемости и старение населения,",
            "grammar_points": [
                {
                    "surface_form": "を",
                    "category": "particle",
                    "grammar_name": "Direct object marker",
                    "detailed_explanation_ru": "Показывает объект действия.",
                    "role_in_sentence": "Отмечает объект глагола 阻止する.",
                },
                {
                    "surface_form": "する",
                    "category": "verb",
                    "grammar_name": "Dictionary form",
                    "detailed_explanation_ru": "Нейтральная словарная форма глагола.",
                    "role_in_sentence": "Входит в состав глагола 阻止する.",
                },
                {
                    "surface_form": "ため",
                    "category": "grammar pattern",
                    "grammar_name": "Purpose expression",
                    "detailed_explanation_ru": "Конструкция для выражения цели: «для того чтобы».",
                    "role_in_sentence": "Показывает цель последующего действия.",
                },
            ],
            "image_prompt": "...",
        }
    ]

    example_output_dir = Path("./my_project")
    stats = import_sentences_to_anki(example_output_dir, example_data)
    print(stats)
