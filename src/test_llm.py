from process_llm import semi_manual_processing
from pathlib import Path
import json

output_dir = Path("D:\extract_audio_for_anki_cards\output\IOSYS - 22世紀のネコ型メイドロボ")
path_word = Path("D:\extract_audio_for_anki_cards\output\IOSYS - 22世紀のネコ型メイドロボ\words.json")
lrc_path = Path("D:\extract_audio_for_anki_cards\output\IOSYS - 22世紀のネコ型メイドロボ\IOSYS - 22世紀のネコ型メイドロボ.lrc")

gpt_output = semi_manual_processing(output_dir, path_word, lrc_path)