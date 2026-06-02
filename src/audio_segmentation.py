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


def slice_audio(audio_path: Path, output_dir: Path, gpt_output_data: list[dict]):
    """
    Нарезает аудио на слова и предложения.

    Parameters
    ----------
    audio_path : Path
        Путь к исходному аудиофайлу.
	output_dir : Path
		Путь к рабочей папке.
    gpt_output_data : list[dict]
        Список объектов вида:
        {
            "word": "...",
            "sentence": "...",
            "word_start": 0.0,
            "word_end": 1.2,
            "sentence_start": 0.0,
            "sentence_end": 3.5
        }
    """

    audio = AudioSegment.from_file(audio_path)

    words_dir = output_dir / "words"
    sentences_dir = output_dir / "sentences"

    words_dir.mkdir(parents=True, exist_ok=True)
    sentences_dir.mkdir(parents=True, exist_ok=True)

    word_counter = {}
    sentence_counter = {}

    for item in gpt_output_data:

        # ----------------------
        # WORD
        # ----------------------
        word = item["word"]

        start_ms = int(item["word_start"] * 1000)
        end_ms = int(item["word_end"] * 1000)

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

        start_ms = int(item["sentence_start"] * 1000)
        end_ms = int(item["sentence_end"] * 1000)

        sentence_audio = audio[start_ms:end_ms]

        sentence_name = sanitize_filename(sentence)

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