from import_anki import import_to_anki
from pathlib import Path
import hashlib
output_dir = r"E:\extract_audio_for_anki_cards\output\影森みちる(CV_諸星すみれ) - TVアニメ『BNA ビー・エヌ・エー』OPテーマ「Ready to」"
output_dir = Path(output_dir)

gpt_output_data = [
{
  "word": "息を潜めて",
  "lemma": "息を潜める",
  "reading": "いきをひそめて",
  "furigana": "いきをひそめて",
  "part_of_speech": "慣用表現",
  "pitch_accent": "",
  "translation": "затаив дыхание, скрываться",
  "sentence": "誰もが息を潜めて",
  "sentence_ru": "Все словно затаили дыхание.",
  "word_start": 28.28,
  "word_end": 30.18,
  "sentence_start": 26.48,
  "sentence_end": 30.18,
  "image_prompt": "silent shadow beast hiding in darkness, holding glowing breath as blue mist trapped inside crystal lungs, eerie stillness, high contrast black background, magical atmosphere, striking silhouette, anime fantasy art",
  "confidence": 0.99
}]

import_to_anki(gpt_output_data, output_dir)