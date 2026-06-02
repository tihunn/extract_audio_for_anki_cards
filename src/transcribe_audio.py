import json
import os

import torch
import whisper

from config_loader import load_config


def run_whisper(audio_path, output_dir):

    print("=" * 60)
    print("START: WHISPER")
    print("=" * 60)

    config = load_config()

    # =========================================
    # GPU INFO
    # =========================================

    print(f"CUDA available: {torch.cuda.is_available()}")

    device = "cuda" if torch.cuda.is_available() else "cpu"

    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    # =========================================
    # LOAD MODEL
    # =========================================

    print("Loading Whisper model...")

    model = whisper.load_model(
        "large",
        device=device
    )

    # =========================================
    # TRANSCRIBE
    # =========================================

    print("Transcribing audio...")

    result = model.transcribe(
        str(audio_path),
        language=config["language_transcribe"],
        task="transcribe",
        word_timestamps=True,
        verbose=True,
    )
	
    # =========================================
    # SAVE FULL TEXT WITH SEGMENT BREAKS
    # =========================================

    # Формируем текст с разделением по сегментам (предложениям)
    segmented_text_parts = []

    for seg in result["segments"]:
        # Получаем текст сегмента и удаляем лишние пробелы
        segment_text = seg["text"].strip()
    
        if segment_text:  # Добавляем только непустые сегменты
            segmented_text_parts.append(segment_text)

    # Объединяем с переносами строк
    full_text_with_breaks = "\n".join(segmented_text_parts)

    text_output_path = os.path.join(
        output_dir,
        "transcription.txt"
    )

    with open(text_output_path, "w", encoding="utf-8") as f:
        f.write(full_text_with_breaks)

    # =========================================
    # SAVE WORDS JSON
    # =========================================

    words_data = []

    for seg in result["segments"]:

        if "words" not in seg:
            continue

        for w in seg["words"]:

            words_data.append({
                "word": w["word"].strip(),
                "start": w["start"],
                "end": w["end"]
            })

    words_json_path = os.path.join(
        output_dir,
        "words.json"
    )

    with open(words_json_path, "w", encoding="utf-8") as f:
        json.dump(
            words_data,
            f,
            ensure_ascii=False,
            indent=2
        )

    # =========================================
    # SAVE FULL SEGMENTS JSON
    # =========================================

    segments_json_path = os.path.join(
        output_dir,
        "segments.json"
    )

    with open(segments_json_path, "w", encoding="utf-8") as f:
        json.dump(
            result["segments"],
            f,
            ensure_ascii=False,
            indent=2
        )

    # =========================================
    # DONE
    # =========================================

    print("\nWHISPER FINISHED")
    print(f"Saved text: {text_output_path}")
    print(f"Saved words: {words_json_path}")
    print(f"Saved segments: {segments_json_path}")

    print(f"Total words: {len(words_data)}")
	
    return words_json_path, segments_json_path, full_text_with_breaks	