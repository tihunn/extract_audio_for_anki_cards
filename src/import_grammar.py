import json
import requests
from pathlib import Path


def detect_encoding_auto(file_path):
    """Пробует несколько кодировок и возвращает рабочую"""
    encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1251', 'cp1252', 'latin-1', 'iso-8859-1']
    
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()
            print(f"✅ Найдена рабочая кодировка: {encoding}")
            return encoding
        except UnicodeDecodeError:
            continue
    
    print("⚠️ Не удалось определить кодировку, используем utf-8 с игнорированием ошибок")
    return 'utf-8'


def import_sentences():
    """Импорт предложений в Anki без аудио"""
    
    # Путь к JSON файлу
    json_path = Path(__file__).resolve().parent.parent / 'sentences.json'
    
    # Определяем кодировку
    encoding = detect_encoding_auto(json_path)
    
    # Загружаем JSON
    with open(json_path, 'r', encoding=encoding) as f:
        sentences = json.load(f)
    
    print(f"Загружено предложений: {len(sentences)}")
    
    # Проверяем подключение к AnkiConnect
    try:
        r = requests.post('http://localhost:8765', json={
            "action": "version",
            "version": 6
        }, timeout=5)
        print("✅ AnkiConnect подключён")
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return
    
    # Создаём колоду
    print("\n📚 Создание колоды...")
    result = requests.post('http://localhost:8765', json={
        "action": "createDeck",
        "version": 6,
        "params": {"deck": "Японские предложения"}
    })
    print(f"Колода создана: {result.json()}")
    
    # Создаём модель с тремя полями
    model = {
        "modelName": "Японские предложения",
        "inOrderFields": ["sentence_highlighted", "explanation_ru", "sentence_translation_ru"],
        "css": """
            .card {
                font-family: 'Noto Sans JP', 'Segoe UI', sans-serif;
                text-align: center;
                padding: 20px;
                background: white;
                color: #333;
            }

            .night_mode .card {
                background: #1a1a1a;
                color: #e0e0e0;
            }

            .sentence {
                font-size: 28px;
                font-weight: bold;
                margin: 30px 0;
                line-height: 1.6;
            }

            .explanation {
                font-size: 18px;
                margin: 20px 0;
                padding: 15px;
                background: #f5f5f5;
                border-radius: 10px;
                text-align: left;
            }

            .night_mode .explanation {
                background: #2a2a2a;
            }

            .translation {
                font-size: 20px;
                margin: 20px 0;
                color: #666;
                font-style: italic;
            }

            .night_mode .translation {
                color: #aaa;
            }

            hr {
                margin: 20px auto;
                border: none;
                height: 1px;
                background: #ddd;
                width: 80%;
            }

            @media (max-width: 620px) {
                .sentence {
                    font-size: 22px;
                }
                .explanation {
                    font-size: 14px;
                }
                .translation {
                    font-size: 16px;
                }
            }
        """,
        "cardTemplates": [{
            "Name": "Предложение",
            "Front": """
                <div class="sentence">{{sentence_highlighted}}</div>
            """,
            "Back": """
                {{FrontSide}}
                <hr>
                <div class="explanation">{{explanation_ru}}</div>
                <div class="translation">{{sentence_translation_ru}}</div>
            """
        }]
    }
    
    # Удаляем старую модель если есть
    print("\n📝 Удаление старой модели...")
    requests.post('http://localhost:8765', json={
        "action": "deleteModel",
        "version": 6,
        "params": {"modelName": "Японские предложения"}
    })
    
    # Создаём новую модель
    print("Создание новой модели...")
    result = requests.post('http://localhost:8765', json={
        "action": "createModel",
        "version": 6,
        "params": model
    })
    
    if result.status_code == 200:
        resp = result.json()
        if resp.get("error"):
            print(f"⚠️ {resp['error']}")
        else:
            print("✅ Модель создана")
    else:
        print(f"❌ Ошибка: {result.status_code}")
        return
    
    # Добавляем карточки
    print(f"\n📖 Добавление {len(sentences)} карточек...")
    
    for i, sent in enumerate(sentences):
        note = {
            "deckName": "Японские предложения",
            "modelName": "Японские предложения",
            "fields": {
                "sentence_highlighted": sent.get("sentence_highlighted", ""),
                "explanation_ru": sent.get("explanation_ru", ""),
                "sentence_translation_ru": sent.get("sentence_translation_ru", "")
            }
        }
        
        result = requests.post('http://localhost:8765', json={
            "action": "addNote",
            "version": 6,
            "params": {"note": note}
        })
        
        if result.status_code == 200:
            resp = result.json()
            if resp.get("error"):
                print(f"  ❌ {i+1}. {sent.get('sentence_highlighted', '?')[:30]}... - {resp['error']}")
            else:
                print(f"  ✅ {i+1}. {sent.get('sentence_highlighted', '?')[:30]}...")
        else:
            print(f"  ❌ {i+1}. Ошибка HTTP: {result.status_code}")
    
    print("\n" + "="*50)
    print("✅ ГОТОВО!")
    print("="*50)


if __name__ == "__main__":
    import_sentences()