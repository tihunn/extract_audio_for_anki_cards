from pathlib import Path
from pydub import AudioSegment
import re


def sanitize_filename(text: str, max_length: int = 512) -> str:
    """
    Удаляет недопустимые символы для имени файла.
    """
    text = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", text)
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > max_length:
        text = text[:max_length]

    return text


def slice_audio(
    audio_path: Path,
    output_dir: Path,
    gpt_output_data: list[dict],
    slice_words: bool = True,
):
    """
    Нарезает аудио на слова и/или предложения.

    Parameters
    ----------
    audio_path : Path
        Путь к исходному аудиофайлу.
    output_dir : Path
        Путь к рабочей папке.
    gpt_output_data : list[dict]
        Список объектов вида:
        {
            "surface": "...",        # нужно только если slice_words=True
            "sentence": "...",
            "word_start": 0.0,       # нужно только если slice_words=True
            "word_end": 1.2,         # нужно только если slice_words=True
            "sentence_start": 0.0,
            "sentence_end": 3.5
        }
    slice_words : bool, default True
        Если False — слова не нарезаются и поля word_start/word_end/surface
        не читаются вообще (на случай если их нет в данных).
    """

    audio = AudioSegment.from_file(audio_path)

    sentences_dir = output_dir / "sentences"
    sentences_dir.mkdir(parents=True, exist_ok=True)

    if slice_words:
        words_dir = output_dir / "words"
        words_dir.mkdir(parents=True, exist_ok=True)
        word_counter = {}

    # Здесь будем дедуплицировать предложения по их временным границам,
    # чтобы одно и то же предложение (повторяющееся в нескольких item,
    # т.к. на каждое слово свой item) не нарезалось и не экспортировалось
    # повторно.
    seen_sentences = {}  # (sentence_start, sentence_end) -> file path
    sentence_counter = {}  # sentence_name -> count, для уникальных имён разных предложений с одинаковым текстом

    for item in gpt_output_data:

        # ----------------------
        # WORD (опционально)
        # ----------------------
        if slice_words:
            word = item["surface"]

            start_ms = int(item["word_start"] * 1000)
            end_ms = int(item["word_end"] * 1000)
            # больший захват для слов
            LEFT_PADDING_MS = 150
            RIGHT_PADDING_MS = 500
            start_ms = max(0, start_ms - LEFT_PADDING_MS)
            end_ms = min(len(audio), end_ms + RIGHT_PADDING_MS)

            word_audio = audio[start_ms:end_ms]

            word_name = sanitize_filename(word)

            word_counter[word_name] = word_counter.get(word_name, 0) + 1

            if word_counter[word_name] > 1:
                word_name = f"{word_name}_{word_counter[word_name]}"

            word_file = words_dir / f"{word_name}.mp3"

            word_audio.export(word_file, format="mp3")

        # ----------------------
        # SENTENCE
        # ----------------------
        sentence = item["sentence"]

        sentence_start = item["sentence_start"]
        sentence_end = item["sentence_end"]
        sentence_key = (sentence_start, sentence_end)

        # Если такое предложение (по точным временным границам) уже
        # обработано — пропускаем, чтобы не плодить дубли вида
        # sentence.mp3, sentence_2.mp3, sentence_3.mp3 ...
        if sentence_key in seen_sentences:
            continue

        seen_sentences[sentence_key] = True

        start_ms = int(sentence_start * 1000)
        end_ms = int(sentence_end * 1000)
        end_ms = min(len(audio), end_ms)

        sentence_audio = audio[start_ms:end_ms]

        sentence_name = sanitize_filename(sentence)

        # Эта дедупликация теперь нужна только для случая, когда у двух
        # РАЗНЫХ по времени предложений совпадает текст (и, соответственно,
        # имя файла) — тогда добавляем суффикс, чтобы не перезаписать файл.
        sentence_counter[sentence_name] = (
            sentence_counter.get(sentence_name, 0) + 1
        )

        if sentence_counter[sentence_name] > 1:
            sentence_name = (
                f"{sentence_name}_{sentence_counter[sentence_name]}"
            )

        sentence_file = sentences_dir / f"{sentence_name}.mp3"

        sentence_audio.export(sentence_file, format="mp3")

    print("Готово!")
