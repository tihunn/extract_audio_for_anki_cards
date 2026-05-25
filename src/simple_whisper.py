import whisper
import torch
import json

# Проверка GPU
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"GPU: {torch.cuda.get_device_name(0)}")

# Загружаем модель (large - самая точная, medium - быстрее)
print("Загрузка модели...")
model = whisper.load_model("large", device="cuda" if torch.cuda.is_available() else "cpu")

# Транскрибация с таймингами слов
print("Транскрибация...")
result = model.transcribe(
    "input/11.mp3", 
    language="ja",  # японский
    word_timestamps=True,  # включает тайминги для каждого слова
    task="transcribe"
)

# Сохраняем JSON для нарезки аудио
words_data = []
for seg in result["segments"]:
    if "words" in seg:
        for w in seg["words"]:
            words_data.append({
                "word": w["word"],
                "start": w["start"],
                "end": w["end"]
            })

with open("output/words.json", "w", encoding="utf-8") as f:
    json.dump(words_data, f, ensure_ascii=False, indent=2)

print(f"Готово! Всего слов: {len(words_data)}")
print(f"Текст: output.txt, JSON: words.json")