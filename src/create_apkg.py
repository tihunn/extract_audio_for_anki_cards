import json
import os
import requests
from pathlib import Path
import locale

def create_apkg_from_json():
    """Создаёт APKG файл из твоих JSON и импортирует в Anki через AnkiConnect"""
    
    # Загружаем JSON файлы
    with open(Path(__file__).resolve().parent.parent / 'test.json', 'r', encoding=locale.getpreferredencoding()) as f:
        words = json.load(f)
    
    #with open('anki_deck2_grammar.json', 'r', encoding='utf-8') as f:
     #   grammar = json.load(f)
    
    # Проверяем подключение к AnkiConnect
    try:
        r = requests.post('http://localhost:8765', json={
            "action": "version",
            "version": 6
        })
        if r.status_code != 200:
            print("❌ Anki не запущен или AnkiConnect не установлен")
            print("Запусти Anki и установи дополнение AnkiConnect (код 2055492159)")
            return
        print("✅ AnkiConnect подключён")
    except:
        print("❌ Не могу подключиться к AnkiConnect")
        print("Убедись что Anki запущен")
        return
    
    # Создаём колоды
    print("\n📚 Создание колод...")
    
    # Колода для слов
    requests.post('http://localhost:8765', json={
        "action": "createDeck",
        "version": 6,
        "params": {"deck": "Японский - Слова"}
    })
    
    # Колода для грамматики
    requests.post('http://localhost:8765', json={
        "action": "createDeck",
        "version": 6,
        "params": {"deck": "Японский - Грамматика"}
    })
    
    # Создаём модель для слов
    word_model = {
        "modelName": "Японские слова (аудио)",
        "inOrderFields": ["word", "base_form", "translation_ru", "sentence", "sentence_translation_ru"],
        "css": """
            .card {
                font-family: 'Noto Sans JP', 'Segoe UI', sans-serif;
                font-size: 20px;
                text-align: center;
                padding: 20px;
            }
            .word {
                font-size: 48px;
                font-weight: bold;
                color: #2c3e50;
                margin: 20px 0;
            }
            audio {
                width: 100%;
                margin: 10px 0;
            }
        """,
        "cardTemplates": [
            {
                "Name": "Слово → Перевод",
                "Front": """
                    <div class="word">{{word}}</div>
                    {{#audio_word}}<audio controls src="{{audio_word}}"></audio>{{/audio_word}}
                """,
                "Back": """
                    {{FrontSide}}
                    <hr>
                    <div><b>Начальная форма:</b> {{base_form}}</div>
                    <div><b>Перевод:</b> {{translation_ru}}</div>
                    <div><b>Предложение:</b> {{sentence}}</div>
                    <div><b>Перевод:</b> {{sentence_translation_ru}}</div>
                    {{#audio_sentence}}<audio controls src="{{audio_sentence}}"></audio>{{/audio_sentence}}
                """
            }
        ]
    }
    
    # Создаём модель для грамматики
    '''grammar_model = {
        "modelName": "Японская грамматика (аудио)",
        "inOrderFields": ["sentence", "explanation", "translation"],
        "css": """
            .card {
                font-family: 'Noto Sans JP', sans-serif;
                font-size: 20px;
                text-align: center;
                padding: 20px;
            }
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
        """,
        "cardTemplates": [
            {
                "Name": "Грамматика",
                "Front": """
                    <div>{{sentence}}</div>
                    {{#audio}}<audio controls src="{{audio}}"></audio>{{/audio}}
                """,
                "Back": """
                    {{FrontSide}}
                    <hr>
                    <div><b>Объяснение:</b> {{explanation}}</div>
                    <div><b>Перевод:</b> {{translation}}</div>
                """
            }
        ]
    }
    
    # Регистрируем модели
    print("📝 Создание типов карточек...")
    requests.post('http://localhost:8765', json={
        "action": "createModel",
        "version": 6,
        "params": word_model
    })
    
    requests.post('http://localhost:8765', json={
        "action": "createModel",
        "version": 6,
        "params": grammar_model
    })
    '''
    
    # Добавляем карточки слов
    print(f"\n📖 Добавление {len(words)} карточек слов...")
    for i, word in enumerate(words):
        # Подготавливаем аудио теги в правильном формате
        audio_word_tag = f'<audio controls src="{word["audio_word_path"]}"></audio>' if word.get("audio_word_path") else ""
        audio_sentence_tag = f'<audio controls src="{word["audio_sentence_path"]}"></audio>' if word.get("audio_sentence_path") else ""
        
        note = {
            "deckName": "Японский - Слова",
            "modelName": "Японские слова (аудио)",
            "fields": {
                "word": word["word"],
                "base_form": word["base_form"],
                "translation_ru": word["translation_ru"],
                "sentence": word["sentence"],
                "sentence_translation_ru": word["sentence_translation_ru"]
            },
            "audio": [
                {
                    "url": f"file:///{Path(__file__).resolve().parent / 'output' / word['audio_word_path'] }",
                    "filename": f"{i}.mp3",
                    "fields": ["audio_word"]
                },
                {
                    "url": f"file:///{Path(__file__).resolve().parent / 'output' / word['audio_sentence_path']}",
                    "filename": f"{i}.mp3",
                    "fields": ["audio_sentence"]
                }
            ] if word.get("audio_word_path") else []
        }
        
        result = requests.post('http://localhost:8765', json={
            "action": "addNote",
            "version": 6,
            "params": {"note": note}
        })
        
        if result.status_code == 200:
            print(f"  ✅ {i+1}. {word['word']}")
        else:
            print(f"  ❌ {i+1}. {word['word']} - ошибка")
    '''
    # Добавляем карточки грамматики
    print(f"\n📖 Добавление {len(grammar)} карточек грамматики...")
    for i, item in enumerate(grammar):
        # Заменяем ** на HTML теги
        sentence_html = item["sentence_highlighted"].replace("**", '<span class="highlight">', 1)
        sentence_html = sentence_html.replace("**", '</span>', 1)
        
        note = {
            "deckName": "Японский - Грамматика",
            "modelName": "Японская грамматика (аудио)",
            "fields": {
                "sentence": sentence_html,
                "explanation": item["explanation_ru"],
                "translation": item["sentence_translation_ru"]
            },
            "audio": [
                {
                    "url": f"file:///{Path(__file__).resolve().parent / 'output' / (item['audio_path'])}",
                    "filename": f"{i}.mp3",
                    "fields": ["audio"]
                }
            ] if item.get("audio_path") else []
        }
        
        result = requests.post('http://localhost:8765', json={
            "action": "addNote",
            "version": 6,
            "params": {"note": note}
        })
        
        if result.status_code == 200:
            print(f"  ✅ {i+1}. {item['sentence_highlighted'][:30]}...")
        else:
            print(f"  ❌ {i+1}. Ошибка")
    '''

    print("\n" + "="*50)
    print("✅ ГОТОВО!")
    print("="*50)
    print("Открой Anki и увидишь новые колоды с карточками")
    print("Аудио будет работать автоматически")

if __name__ == "__main__":
    create_apkg_from_json()