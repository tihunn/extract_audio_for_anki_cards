from pathlib import Path
from config_loader import load_config
import json
from typing import Dict, Any, Optional
import os
from rich.console import Console


def compact_json_content(json_path: Path, remove_empty: bool = True) -> Dict[str, Any]:
    """
    Загружает и компактизирует JSON файл
    - remove_empty: удалять ли пустые значения (None, "", [], {})
    """
    if not json_path.exists():
        raise FileNotFoundError(f"JSON файл не найден: {json_path}")
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    def compact_dict(obj):
        """Рекурсивно удаляет пустые значения"""
        if isinstance(obj, dict):
            if remove_empty:
                # Удаляем пустые ключи
                return {
                    k: compact_dict(v) for k, v in obj.items() 
                    if v not in (None, "", [], {}) and v is not None
                }
            else:
                return {k: compact_dict(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            if remove_empty:
                # Удаляем пустые элементы из списка
                return [compact_dict(item) for item in obj if item not in (None, "", [], {})]
            else:
                return [compact_dict(item) for item in obj]
        else:
            return obj
    
    compacted_data = compact_dict(data)
    return compacted_data

def read_lrc_file(lrc_path: Path) -> str:
    """Читает LRC файл с текстом песни"""
    if not lrc_path.exists():
        raise FileNotFoundError(f"LRC файл не найден: {lrc_path}")
    
    with open(lrc_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()
    
    return content

def create_unified_prompt(
    words_json_path: Path,
    lrc_path: Path,
    compact_json: bool = True,
) -> str:
    """
    Создаёт объединённый промпт из трёх источников
    
    Args:
        words_json_path: путь к words.json
        lrc_path: путь к LRC файлу
        compact_json: компактизировать ли JSON
    """
    # 1. Загружаем конфиг с основным промптом
    config = load_config()
    main_prompt = config.get("promt_gpt", "")
    
    # 2. Загружаем и компактизируем JSON
    try:
        json_data = compact_json_content(words_json_path, remove_empty=compact_json)

        # Компактный формат без лишних пробелов
        json_str = json.dumps(json_data, ensure_ascii=False, separators=(',', ':') if compact_json else None)
            
    except Exception as e:
        json_str = f"Ошибка загрузки JSON: {str(e)}"
    
    # 3. Загружаем LRC файл
    try:
        lrc_content = read_lrc_file(lrc_path)
    except Exception as e:
        lrc_content = f"Ошибка загрузки LRC: {str(e)}"
    
    # 4. Формируем финальный промпт с чёткими секциями
    prompt_sections = [
        main_prompt,
		
        "words.json",
        json_str,
		
        f"(LRC файл) - {lrc_path.name}",
        lrc_content
    ]
    
    unified_prompt = "\n".join(prompt_sections)
    
    return unified_prompt

def semi_manual_processing(output_dir, words_json_path, lrc_path):
    console = Console()
	
    gpt_promt = create_unified_prompt(words_json_path, lrc_path)
	
    console.print("[red]Промпт для копировапния начинается после этих слов [/red] \n\n")
    print(gpt_promt)
	
    # Создание файла в который нужно будет вручную поместить ответ 
    gpt_output = os.path.join(output_dir, "anki unique words.json")
    with open(gpt_output, "w", encoding="utf-8") as file:
        json.dump([], file)
	
    console.print(f"\n\n Отправте промпт в chatGPT, скопируйте ответ в [bold cyan] {gpt_output} [/bold cyan]")
    input(f" Нажмите чтобы продолжить")
	
    return gpt_output	