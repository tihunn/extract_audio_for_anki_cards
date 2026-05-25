import json
import requests
from pathlib import Path
import locale
import base64


def detect_encoding_auto(file_path):
    """Пробует несколько кодировок и возвращает рабочую"""
    encodings_to_try = ['utf-8', 'utf-8-sig', 'cp1251', 'cp1252', 'latin-1', 'iso-8859-1']
    
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                f.read()  # Пробуем прочитать
            print(f"✅ Найдена рабочая кодировка: {encoding}")
            return encoding
        except UnicodeDecodeError:
            continue
    
    # Если ничего не подошло, возвращаем utf-8 с ignore ошибками
    print("⚠️ Не удалось определить кодировку, используем utf-8 с игнорированием ошибок")
    return 'utf-8'
	
def import_words_with_audio():
    """Импорт слов в Anki с аудиофайлами"""
    
    # Путь к твоему JSON файлу
    json_path = Path(__file__).resolve().parent.parent / 'test.json'
    
	# Определяем кодировку
    encoding = detect_encoding_auto(json_path)
	
    # Загружаем JSON
    with open(json_path, 'r', encoding=encoding) as f:
        words = json.load(f)
    
    print(f"Загружено слов: {len(words)}")
    
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
        "params": {"deck": "Японский - Слова с аудио"}
    })
    print(f"Колода создана: {result.json()}")
    
    # Создаём модель с поддержкой аудио
    model = {
        "modelName": "Японские слова с аудио",
        "inOrderFields": ["word", "base_form", "translation_ru", "sentence", "sentence_translation_ru", "audio_word", "audio_sentence"],
        "css": """
            @import url("https://fonts.googleapis.com/css2?family=Noto+Sans+JP&display=swap");

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

			.word {
				font-size: 64px;
				font-weight: bold;
				margin: 30px 0;
				
			}

			.audio-container {
				margin: 20px 0;
			}

			/* Стилизация стандартной кнопки Anki (убираем лишние стили) */
			.soundLink, .replaybutton {
				background: none !important;
				border: none !important;
				padding: 0 !important;
				margin: 10px 0 !important;
			}

			hr {
				margin: 20px auto;
				border: none;
				height: 1px;
				background: #ddd;
				width: 80%;
			}

			.night_mode hr {
				background: #444;
			}

			/* Контейнер для информации и картинки */
			.info-container {
				display: flex;
				justify-content: center;
				align-items: center;
				gap: 30px;
				flex-wrap: wrap;
				margin: 20px 0;
			}

			/* Блок с текстом (начальная форма и перевод) */
			.info-text {
				text-align: center;
			}

			.base-form, .translation {
				font-size: 18px;
				padding: 8px 16px;
				background: #f0f0f0;
				border-radius: 8px;
				margin: 8px 0;
				display: block;
			}

			.night_mode .base-form,
			.night_mode .translation {
				background: #2a2a2a;
			}

			.base-form {
				color: #483D8B;
				font-weight: bold;
			}

			/* Контейнер для картинок — горизонтальный ряд */
			.images-container {
				display: flex;
				flex-wrap: wrap;
				justify-content: center;
				gap: 10px;
			}

			/* Стиль для картинок */
			.images-container img {
				max-height: 150px;
				max-width: 150px;
				object-fit: contain;
				border-radius: 8px;
				cursor: pointer;
				transition: transform 0.2s;
				background: #f0f0f0;
				padding: 3px;
			}

			.night_mode .images-container img {
				background: #2a2a2a;
			}

			.images-container img:hover {
				transform: scale(1.05);
			}

			.sentence-block {
				background: #f5f5f5;
				padding: 15px;
				border-radius: 10px;
				margin: 20px auto;
				max-width: 600px;
			}

			.night_mode .sentence-block {
				background: #2a2a2a;
			}

			.sentence-text {
				font-size: 18px;
				line-height: 1.6;
				margin-bottom: 10px;
			}

			.sentence-translation {
				font-size: 14px;
				color: #666;
				font-style: italic;
			}

			.night_mode .sentence-translation {
				color: #aaa;
			}

			/* Мобильная версия */
			@media (max-width: 620px) {
				.word {
					font-size: 48px;
				}
				
				.info-container {
					gap: 15px;
				}
				
				.images-container img {
					max-height: 100px;
					max-width: 100px;
				}
				
				.base-form, .translation {
					font-size: 14px;
					padding: 5px 12px;
				}
				
				.sentence-text {
					font-size: 14px;
				}
			}
        """,
		"cardTemplates": [{
			"Name": "Слово с аудио",
			"Front": """
				<div class="word">{{word}}</div>

				<div class="audio-container">
					{{audio_word}}
				</div>

				<script>
					const audioBtn = document.querySelector('.soundLink, .replaybutton');
					if (audioBtn) {
						audioBtn.addEventListener('click', function() {
							const allAudios = document.querySelectorAll('audio');
							allAudios.forEach(audio => {
								if (audio !== this) {
									audio.pause();
									audio.currentTime = 0;
								}
							});
						});
					}
				</script>
			""",
			"Back": """
				{{FrontSide}}
				
				<hr>
				
				<div class="info-container">
					<div class="info-text">
						<div class="base-form">{{base_form}}</div>
						<div class="translation">{{translation_ru}}</div>
					</div>
					
					<div class="images-container">
						{{image}}
					</div>
				</div>

				<div class="sentence-block">
					<div class="sentence-text">{{sentence}}</div>
					<div class="sentence-translation">{{sentence_translation_ru}}</div>
				</div>

				<div class="audio-container">
					{{audio_sentence}}
				</div>
			"""
		}]
    }
    
    # Удаляем старую модель если есть
    print("\n📝 Удаление старой модели...")
    requests.post('http://localhost:8765', json={
        "action": "deleteModel",
        "version": 6,
        "params": {"modelName": "Японские слова с аудио"}
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
    
    # Базовый путь к аудиофайлам
    audio_base_path = Path(__file__).resolve().parent.parent / 'output' 
    
    # Добавляем карточки
    print(f"\n📖 Добавление {len(words)} карточек...")
    
    for i, word in enumerate(words):
        # Получаем пути к аудио
        audio_word_rel = word.get("audio_word_path", "")
        audio_sentence_rel = word.get("audio_sentence_path", "")
    
        audio_word_path = audio_base_path / audio_word_rel
        audio_sentence_path = audio_base_path / audio_sentence_rel
    
        # Сначала загружаем аудиофайлы в Anki через storeMediaFile
        audio_word_filename = None
        audio_sentence_filename = None
    
        # Загружаем аудио слова
        if audio_word_path.exists():
            # Читаем файл в base64
            
            with open(audio_word_path, 'rb') as f:
                audio_data = base64.b64encode(f.read()).decode('utf-8')
        
            # Отправляем в Anki
            store_result = requests.post('http://localhost:8765', json={
                "action": "storeMediaFile",
                "version": 6,
                "params": {
                    "filename": audio_word_path.name,
                    "data": audio_data
                }
            })
        
            if store_result.status_code == 200:
                resp = store_result.json()
                if not resp.get("error"):
                    audio_word_filename = audio_word_path.name
                    print(f"  📁 Загружено аудио слова: {audio_word_path.name}")
                else:
                    print(f"  ⚠️ Ошибка загрузки аудио слова: {resp['error']}")
            else:
                print(f"  ⚠️ Ошибка HTTP при загрузке аудио слова")
    
        # Загружаем аудио предложения
        if audio_sentence_path.exists():
            with open(audio_sentence_path, 'rb') as f:
                audio_data = base64.b64encode(f.read()).decode('utf-8')
        
            store_result = requests.post('http://localhost:8765', json={
                "action": "storeMediaFile",
                "version": 6,
                "params": {
                    "filename": audio_sentence_path.name,
                    "data": audio_data
                }
            })
        
            if store_result.status_code == 200:
                resp = store_result.json()
                if not resp.get("error"):
                    audio_sentence_filename = audio_sentence_path.name
                    print(f"  📁 Загружено аудио предложения: {audio_sentence_path.name}")
                else:
                    print(f"  ⚠️ Ошибка загрузки аудио предложения: {resp['error']}")
    
        # Создаём заметку с тегами [sound:...]
        note = {
            "deckName": "Японский - Слова с аудио",
            "modelName": "Японские слова с аудио",
            "fields": {
                "word": word.get("word", ""),
                "base_form": word.get("base_form", ""),
                "translation_ru": word.get("translation_ru", ""),
                "sentence": word.get("sentence", ""),
                "sentence_translation_ru": word.get("sentence_translation_ru", ""),
                "audio_word": f"[sound:{audio_word_filename}]" if audio_word_filename else "",
                "audio_sentence": f"[sound:{audio_sentence_filename}]" if audio_sentence_filename else ""
            }
        }
    
        # Отправляем запрос на создание заметки
        result = requests.post('http://localhost:8765', json={
            "action": "addNote",
            "version": 6,
            "params": {"note": note}
        })
    
        if result.status_code == 200:
            resp = result.json()
            if resp.get("error"):
                print(f"  ❌ {i+1}. {word.get('word')} - {resp['error']}")
                # Если заметка не создалась, удаляем загруженные аудиофайлы
                if audio_word_filename:
                    requests.post('http://localhost:8765', json={
                        "action": "deleteMediaFile",
                        "version": 6,
                        "params": {"filename": audio_word_filename}
                    })
                if audio_sentence_filename:
                    requests.post('http://localhost:8765', json={
                        "action": "deleteMediaFile",
                        "version": 6,
                        "params": {"filename": audio_sentence_filename}
                    })
            else:
                print(f"  ✅ {i+1}. {word.get('word')}")
        else:
            print(f"  ❌ {i+1}. Ошибка HTTP: {result.status_code}")
            # Если заметка не создалась, удаляем загруженные аудиофайлы
            if audio_word_filename:
                requests.post('http://localhost:8765', json={
                    "action": "deleteMediaFile",
                    "version": 6,
                    "params": {"filename": audio_word_filename}
                })
            if audio_sentence_filename:
                requests.post('http://localhost:8765', json={
                    "action": "deleteMediaFile",
                    "version": 6,
                    "params": {"filename": audio_sentence_filename}
                })
    
        print("\n" + "="*50)
        print("✅ ГОТОВО!")
        print("="*50)
        

if __name__ == "__main__":
    import_words_with_audio()