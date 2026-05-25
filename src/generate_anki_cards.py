import json
import os
import subprocess
import requests
import uuid
import time
import csv
from pathlib import Path
from pydub import AudioSegment
from typing import Dict, List, Optional

# Добавь эти функции в generate_anki_cards.py

import csv
import os
import shutil
from pathlib import Path

class AnkiMediaPreparer:
    def __init__(self, output_dir="output"):
        self.output_dir = Path(output_dir)
        self.media_dir = self.output_dir / "anki_media"
        self.media_dir.mkdir(exist_ok=True)
        
    def prepare_audio_for_anki(self, audio_source_path: Path, dest_filename: str) -> str:
        """Подготавливает аудио файл для Anki и возвращает тег [sound:...]"""
        dest_path = self.media_dir / dest_filename
        shutil.copy2(audio_source_path, dest_path)
        return f"[sound:{dest_filename}]"
    
    def prepare_image_for_anki(self, image_source_path: Path, dest_filename: str) -> str:
        """Подготавливает изображение для Anki"""
        dest_path = self.media_dir / dest_filename
        shutil.copy2(image_source_path, dest_path)
        return dest_filename

class AnkiCardGenerator:
    # ... (предыдущий код) ...
    
    def generate_deck1_csv_with_audio_tags(self, words_data: List[Dict]):
        """Генерирует CSV с тегами [sound:...] для автоматического импорта аудио"""
        
        csv_path = self.output_dir / "deck1_anki_cards.csv"
        media_preparer = AnkiMediaPreparer(self.output_dir)
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "word", "base_form", "translation_ru", "sentence", 
                "sentence_translation_ru", "image", "audio_word", "audio_sentence"
            ])
            
            for idx, word in enumerate(words_data):
                print(f"\n🔄 Обработка слова {idx+1}/{len(words_data)}: {word['word']}")
                
                # Создаём уникальные имена файлов
                safe_word = "".join(c for c in word['word'] if c.isalnum() or c in (' ', '-', '_')).strip()
                word_audio_filename = f"word_{idx:04d}_{safe_word}.mp3"
                sentence_audio_filename = f"sentence_{idx:04d}.mp3"
                image_filename = f"image_{idx:04d}.png"
                
                # Вырезаем аудио (как раньше)
                word_audio_path = self.audio_words_dir / word_audio_filename
                sentence_audio_path = self.audio_sentences_dir / sentence_audio_filename
                image_path = self.images_dir / image_filename
                
                self.extract_audio(word['word_start'], word['word_end'], str(word_audio_path))
                self.extract_audio(word['sentence_start'], word['sentence_end'], str(sentence_audio_path))
                
                # Генерируем изображение
                print(f"🎨 Генерация изображения для: {word['word']}")
                self.comfyui.generate_image(word['image_prompt'], str(image_path), self.workflow)
                
                # Подготавливаем для Anki (копируем в media папку и создаём теги)
                word_audio_tag = media_preparer.prepare_audio_for_anki(word_audio_path, word_audio_filename)
                sentence_audio_tag = media_preparer.prepare_audio_for_anki(sentence_audio_path, sentence_audio_filename)
                image_ref = media_preparer.prepare_image_for_anki(image_path, image_filename)
                
                writer.writerow([
                    word['word'],
                    word['base_form'],
                    word['translation_ru'],
                    word['sentence'],
                    word['sentence_translation_ru'],
                    image_ref,
                    word_audio_tag,
                    sentence_audio_tag
                ])
                
                time.sleep(2)  # Пауза между генерациями
        
        print(f"\n✅ CSV для первой колоды создан: {csv_path}")
        print(f"📁 Медиафайлы для Anki в папке: {media_preparer.media_dir}")
        return csv_path, media_preparer.media_dir
    
    def generate_deck2_csv_with_audio_tags(self, grammar_data: List[Dict]):
        """Генерирует CSV для второй колоды с тегами [sound:...]"""
        
        csv_path = self.output_dir / "deck2_anki_cards.csv"
        media_preparer = AnkiMediaPreparer(self.output_dir)
        
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "sentence_highlighted", "explanation_ru", 
                "sentence_translation_ru", "audio"
            ])
            
            for idx, grammar in enumerate(grammar_data):
                print(f"\n🔄 Обработка грамматики {idx+1}/{len(grammar_data)}")
                
                audio_filename = f"grammar_{idx:04d}.mp3"
                audio_path = self.audio_deck2_dir / audio_filename
                
                # Вырезаем аудио
                self.extract_audio(
                    grammar['sentence_start'], 
                    grammar['sentence_end'], 
                    str(audio_path)
                )
                
                # Подготавливаем тег для Anki
                audio_tag = media_preparer.prepare_audio_for_anki(audio_path, audio_filename)
                
                # Форматируем предложение с HTML для выделения
                sentence_html = grammar['sentence_highlighted'].replace(
                    '**', '<span class="highlight">'
                ).replace('**', '</span>', 1)
                
                writer.writerow([
                    sentence_html,
                    grammar['explanation_ru'],
                    grammar['sentence_translation_ru'],
                    audio_tag
                ])
        
        print(f"\n✅ CSV для второй колоды создан: {csv_path}")
        return csv_path, media_preparer.media_dir
    
    def create_anki_package(self, deck1_data, deck2_data):
        """Создаёт готовый пакет для Anki (CSV + медиа)"""
        
        # Генерируем CSV с тегами
        deck1_csv, deck1_media = self.generate_deck1_csv_with_audio_tags(deck1_data)
        deck2_csv, deck2_media = self.generate_deck2_csv_with_audio_tags(deck2_data)
        
        # Создаём архив для удобства
        import zipfile
        import datetime
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = self.output_dir / f"anki_import_package_{timestamp}.zip"
        
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            # Добавляем CSV файлы
            zipf.write(deck1_csv, arcname="deck1_words.csv")
            zipf.write(deck2_csv, arcname="deck2_grammar.csv")
            
            # Добавляем все медиафайлы
            for media_file in deck1_media.glob("*"):
                zipf.write(media_file, arcname=f"media/{media_file.name}")
            for media_file in deck2_media.glob("*"):
                if media_file not in deck1_media.glob("*"):  # Избегаем дубликатов
                    zipf.write(media_file, arcname=f"media/{media_file.name}")
            
            # Добавляем инструкцию
            instruction = self.create_import_instruction()
            zipf.writestr("IMPORT_INSTRUCTION.txt", instruction)
        
        print(f"\n📦 Создан архив для импорта: {zip_path}")
        return zip_path
    
    def create_import_instruction(self):
        """Создаёт подробную инструкцию по импорту"""
        return """
📚 ИНСТРУКЦИЯ ПО ИМПОРТУ В ANKI
================================

ШАГ 1: Подготовка медиафайлов
-----------------------------
1. Распакуйте архив
2. Скопируйте ВСЕ файлы из папки /media/ в:
   - Windows: %APPDATA%\\Anki2\\[Ваше_имя_пользователя]\\collection.media\\
   - Mac: ~/Library/Application Support/Anki2/[Ваше_имя_пользователя]/collection.media/
   - Linux: ~/.local/share/Anki2/[Ваше_имя_пользователя]/collection.media/

ШАГ 2: Создание типа записи для Deck 1 (слова)
---------------------------------------------
1. Откройте Anki → Инструменты → Управление типами записей
2. Добавить → Назовите: "Японские слова с аудио"
3. Добавьте поля: word, base_form, translation_ru, sentence, sentence_translation_ru, image, audio_word, audio_sentence
4. Настройте шаблоны (см. ниже)

ШАГ 3: Импорт Deck 1
-------------------
1. Файл → Импорт
2. Выберите deck1_words.csv
3. Тип записи: "Японские слова с аудио"
4. Колода: создайте новую "Японский - Слова"
5. Убедитесь, что поля соответствуют:
   - word → word
   - base_form → base_form
   - translation_ru → translation_ru
   - sentence → sentence
   - sentence_translation_ru → sentence_translation_ru
   - image → image
   - audio_word → audio_word
   - audio_sentence → audio_sentence
6. Включите опции:
   ✓ Разрешить HTML в полях
   ✓ Поля содержат ссылки на медиафайлы

ШАГ 4: Deck 2 (грамматика) - аналогично
--------------------------------------
Тип записи: "Японская грамматика"
Поля: sentence_highlighted, explanation_ru, sentence_translation_ru, audio

ШАГ 5: CSS стили
---------------
Добавьте в настройки типа записи:

.highlight { 
    color: #e74c3c; 
    font-weight: bold; 
    background: #ffeaea;
    padding: 2px 5px;
    border-radius: 3px;
}

audio {
    width: 100%;
    margin: 10px 0;
}

img {
    max-width: 300px;
    border-radius: 10px;
}

ГОТОВО! 🎉
"""



class ComfyUIGenerator:
    def __init__(self, comfyui_url="http://127.0.0.1:8188"):
        self.comfyui_url = comfyui_url
        self.client_id = str(uuid.uuid4())
        
    def queue_prompt(self, workflow):
        """Отправляет workflow в ComfyUI"""
        p = {"prompt": workflow, "client_id": self.client_id}
        response = requests.post(f"{self.comfyui_url}/prompt", json=p)
        return response.json()
    
    def get_image(self, filename, subfolder, folder_type):
        """Получает сгенерированное изображение из ComfyUI"""
        data = {"filename": filename, "subfolder": subfolder, "type": folder_type}
        response = requests.get(f"{self.comfyui_url}/view", params=data)
        return response.content
    
    def generate_image(self, prompt: str, output_path: str, workflow_template: Dict) -> bool:
        """Генерирует изображение по промпту используя ComfyUI"""
        try:
            # Обновляем промпт в workflow
            workflow = workflow_template.copy()
            
            # Находим ноду с текстовым промптом (обычно CLIP Text Encode)
            for node_id, node in workflow.items():
                if node.get("class_type") == "CLIPTextEncode":
                    if node.get("_meta", {}).get("title") == "positive":
                        node["inputs"]["text"] = prompt
                        break
            
            # Отправляем в очередь
            result = self.queue_prompt(workflow)
            prompt_id = result['prompt_id']
            
            # Ждём завершения генерации
            while True:
                time.sleep(1)
                response = requests.get(f"{self.comfyui_url}/history/{prompt_id}")
                history = response.json()
                if prompt_id in history:
                    # Получаем выходные изображения
                    outputs = history[prompt_id]['outputs']
                    for node_id, node_output in outputs.items():
                        if 'images' in node_output:
                            for image in node_output['images']:
                                img_data = self.get_image(
                                    image['filename'], 
                                    image['subfolder'], 
                                    image['type']
                                )
                                with open(output_path, 'wb') as f:
                                    f.write(img_data)
                                print(f"✅ Изображение сохранено: {output_path}")
                                return True
                    break
            return False
        except Exception as e:
            print(f"❌ Ошибка генерации изображения: {e}")
            return False

class AnkiCardGenerator:
    def __init__(self, audio_file_path: str, comfyui_workflow_path: str):
        self.audio_file_path = Path(audio_file_path)
        self.comfyui_workflow_path = Path(comfyui_workflow_path)
        self.audio = AudioSegment.from_mp3(str(self.audio_file_path))
        
        # Создаём папки для выходных файлов
        self.output_dir = Path("output")
        self.audio_words_dir = self.output_dir / "deck1_audio_words"
        self.audio_sentences_dir = self.output_dir / "deck1_audio_sentences"
        self.audio_deck2_dir = self.output_dir / "deck2_audio"
        self.images_dir = self.output_dir / "images"
        
        for dir_path in [self.audio_words_dir, self.audio_sentences_dir, 
                         self.audio_deck2_dir, self.images_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        # Загружаем workflow ComfyUI
        with open(comfyui_workflow_path, 'r') as f:
            self.workflow = json.load(f)
        
        self.comfyui = ComfyUIGenerator()
    
    def extract_audio(self, start_sec: float, end_sec: float, output_path: str):
        """Вырезает аудиофрагмент по таймкодам"""
        try:
            start_ms = int(start_sec * 1000)
            end_ms = int(end_sec * 1000)
            fragment = self.audio[start_ms:end_ms]
            fragment.export(output_path, format="mp3")
            print(f"✅ Аудио сохранено: {output_path}")
            return True
        except Exception as e:
            print(f"❌ Ошибка вырезания аудио: {e}")
            return False
    
    def generate_deck1_csv(self, words_data: List[Dict]):
        """Генерирует CSV для первой колоды (уникальные слова)"""
        csv_path = self.output_dir / "deck1_anki_cards.csv"
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Заголовки полей
            writer.writerow([
                "word", "base_form", "translation_ru", "sentence", 
                "sentence_translation_ru", "image_path", "audio_word_path", 
                "audio_sentence_path"
            ])
            
            for idx, word in enumerate(words_data):
                print(f"\n🔄 Обработка слова {idx+1}/{len(words_data)}: {word['word']}")
                
                # Пути к файлам
                word_audio_path = self.audio_words_dir / f"word_{idx:04d}_{word['word']}.mp3"
                sentence_audio_path = self.audio_sentences_dir / f"sentence_{idx:04d}.mp3"
                image_path = self.images_dir / f"image_{idx:04d}.png"
                
                # Вырезаем аудио слова
                self.extract_audio(word['word_start'], word['word_end'], str(word_audio_path))
                
                # Вырезаем аудио предложения
                self.extract_audio(word['sentence_start'], word['sentence_end'], str(sentence_audio_path))
                
                # Генерируем изображение
                print(f"🎨 Генерация изображения для: {word['word']}")
                self.comfyui.generate_image(
                    word['image_prompt'], 
                    str(image_path), 
                    self.workflow
                )
                
                # Добавляем строку в CSV (относительные пути)
                writer.writerow([
                    word['word'],
                    word['base_form'],
                    word['translation_ru'],
                    word['sentence'],
                    word['sentence_translation_ru'],
                    f"images/image_{idx:04d}.png",
                    f"deck1_audio_words/word_{idx:04d}_{word['word']}.mp3",
                    f"deck1_audio_sentences/sentence_{idx:04d}.mp3"
                ])
                
                time.sleep(2)  # Пауза между генерациями
        
        print(f"\n✅ CSV для первой колоды создан: {csv_path}")
        return csv_path
    
    def generate_deck2_csv(self, grammar_data: List[Dict]):
        """Генерирует CSV для второй колоды (грамматика)"""
        csv_path = self.output_dir / "deck2_anki_cards.csv"
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "sentence_highlighted", "explanation_ru", 
                "sentence_translation_ru", "audio_path"
            ])
            
            for idx, grammar in enumerate(grammar_data):
                print(f"\n🔄 Обработка грамматики {idx+1}/{len(grammar_data)}")
                
                audio_path = self.audio_deck2_dir / f"grammar_{idx:04d}.mp3"
                
                # Вырезаем аудио предложения
                self.extract_audio(
                    grammar['sentence_start'], 
                    grammar['sentence_end'], 
                    str(audio_path)
                )
                
                # Форматируем предложение с HTML для выделения красным
                # В Anki можно использовать CSS: .highlight { color: red; font-weight: bold; }
                sentence_html = grammar['sentence_highlighted'].replace(
                    '**', '<span class="highlight">'
                ).replace(
                    '**', '</span>', 1
                )  # Простое преобразование, можно улучшить
                
                # Добавляем строку в CSV
                writer.writerow([
                    sentence_html,
                    grammar['explanation_ru'],
                    grammar['sentence_translation_ru'],
                    f"deck2_audio/grammar_{idx:04d}.mp3"
                ])
        
        print(f"\n✅ CSV для второй колоды создан: {csv_path}")
        return csv_path
    
    def create_anki_apkg_instruction(self):
        """Создаёт инструкцию для импорта в Anki"""
        instruction = """
ИНСТРУКЦИЯ ПО ИМПОРТУ В ANKI
================================

1. Откройте Anki
2. Создайте новую колоду:
   - Deck 1: "Японский - Уникальные слова"
   - Deck 2: "Японский - Грамматика"

3. Для каждой колоды настройте типы карточек:

   DECK 1 (Уникальные слова):
   --------------------------
   Поля:
   - word (Слово) - на лицевой стороне
   - base_form (Начальная форма)
   - translation_ru (Перевод)
   - sentence (Предложение)
   - sentence_translation_ru (Перевод предложения)
   - image_path (Картинка)
   - audio_word_path (Аудио слова)
   - audio_sentence_path (Аудио предложения)

   Карточка:
   Лицевая сторона:
   {{word}}
   {{audio_word_path}}

   Обратная сторона:
   {{base_form}}<br>
   {{translation_ru}}<br>
   <hr>
   {{sentence}}<br>
   {{sentence_translation_ru}}<br>
   {{audio_sentence_path}}<br>
   <img src="{{image_path}}">

   DECK 2 (Грамматика):
   -------------------
   Поля:
   - sentence_highlighted (Предложение с выделением)
   - explanation_ru (Объяснение)
   - sentence_translation_ru (Перевод)
   - audio_path (Аудио)

   Карточка:
   Лицевая сторона:
   {{sentence_highlighted}}<br>
   {{audio_path}}

   Обратная сторона:
   {{explanation_ru}}<br>
   <hr>
   {{sentence_translation_ru}}

   CSS для Deck 2 (в настройках типа карточки):
   .highlight { color: red; font-weight: bold; }

4. Импорт CSV:
   - Файл → Импорт
   - Выберите deck1_anki_cards.csv или deck2_anki_cards.csv
   - Тип карточки: выберите созданный тип
   - Колода: выберите созданную колоду
   - Разделитель: запятая
   - Разрешить HTML в полях: ДА (для Deck 2)

5. Скопируйте папки с аудио и изображениями в коллекцию Anki:
   - Путь: %APPDATA%\\Anki2\\[пользователь]\\collection.media\\
   - Скопируйте туда содержимое папок:
     * deck1_audio_words/
     * deck1_audio_sentences/
     * deck2_audio/
     * images/
"""
        instruction_path = self.output_dir / "IMPORT_INSTRUCTION.txt"
        with open(instruction_path, 'w', encoding='utf-8') as f:
            f.write(instruction)
        print(f"✅ Инструкция сохранена: {instruction_path}")

def main():
    # Конфигурация
    AUDIO_FILE = "audio/song.mp3"  # Путь к твоему аудиофайлу песни
    DECK1_JSON = "anki_deck1_unique_words.json"
    DECK2_JSON = "anki_deck2_grammar.json"
    COMFYUI_WORKFLOW = "scripts/comfyui_workflow.json"
    
    # Проверка наличия файлов
    if not os.path.exists(AUDIO_FILE):
        print(f"❌ Ошибка: Аудиофайл не найден: {AUDIO_FILE}")
        print("Пожалуйста, поместите файл song.mp3 в папку audio/")
        return
    
    if not os.path.exists(DECK1_JSON):
        print(f"❌ Ошибка: Файл {DECK1_JSON} не найден")
        return
    
    if not os.path.exists(DECK2_JSON):
        print(f"❌ Ошибка: Файл {DECK2_JSON} не найден")
        return
    
    # Загрузка данных
    with open(DECK1_JSON, 'r', encoding='utf-8') as f:
        words_data = json.load(f)
    
    with open(DECK2_JSON, 'r', encoding='utf-8') as f:
        grammar_data = json.load(f)
    
    print(f"📊 Загружено слов: {len(words_data)}")
    print(f"📊 Загружено грамматических конструкций: {len(grammar_data)}")
    
    # Инициализация генератора
    generator = AnkiCardGenerator(AUDIO_FILE, COMFYUI_WORKFLOW)
    
    # Генерация CSV и медиафайлов
    print("\n" + "="*50)
    print("ГЕНЕРАЦИЯ ПЕРВОЙ КОЛОДЫ (Уникальные слова)")
    print("="*50)
    generator.generate_deck1_csv(words_data)
    
    print("\n" + "="*50)
    print("ГЕНЕРАЦИЯ ВТОРОЙ КОЛОДЫ (Грамматика)")
    print("="*50)
    generator.generate_deck2_csv(grammar_data)
    
    # Создание инструкции
    generator.create_anki_apkg_instruction()
    
    print("\n🎉 ВСЕ ГОТОВО!")
    print(f"📁 Результаты сохранены в папке: {generator.output_dir}")

if __name__ == "__main__":
    main()

