from pathlib import Path
from config_loader import load_config
import json
from typing import Dict, Any
import os
from rich.console import Console
import re
import pyperclip


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


def replace_prompt_placeholder(
    search_phrase: str,
    main_prompt: str,
    file_text: str
) -> str:
    """
    Ищет search_phrase в main_prompt и заменяет на file_text.

    Args:
        search_phrase: строка для поиска, например "{word.json}"
        main_prompt: основной промпт
        file_text: содержимое файла

    Returns:
        Готовый промпт с подставленным текстом
    """
    if not main_prompt:
        return file_text

    return main_prompt.replace(search_phrase, file_text)


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
    extract_promt_gpt = config.get("extract_promt_gpt", "")
    
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

    ready_prompt = replace_prompt_placeholder(
        "{word.json}",
        extract_promt_gpt,
        json_str
    )

    ready_prompt = replace_prompt_placeholder(
        "{lyrics.lrc}",
        ready_prompt,
        lrc_content
    )

    return ready_prompt


def clean_lrc_text(lrc_text: str) -> str:
    """
    Удаляет тайминги вида:
    [5:45]
    [12:09]
    [0:00]
    [1:23.456]
    [59:59.999]

    Возвращает чистый текст песни.
    """

    # Удаляем все тайминги
    cleaned = re.sub(
        r'\[\d{1,2}:\d{2}(?:\.\d+)?\]',
        '',
        lrc_text
    )

    # Удаляем пустые строки
    lines = [
        line.strip()
        for line in cleaned.splitlines()
        if line.strip()
    ]

    return "\n".join(lines)


def extract_words_batch(
    json_path: Path,
    batch_size: int,
    start_index: int = 0
):
    """
    Возвращает пакет записей и индекс следующего пакета.

    Returns:
        (text_for_prompt, next_index, has_more)
    """

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    batch = data[start_index:start_index + batch_size]

    result = []

    for item in batch:
        lemma = item.get("lemma", "")
        sentence = item.get("sentence", "")

        result.append(
            f"lemma: {lemma}\nsentence: {sentence}"
        )

    text = "\n\n".join(result)

    next_index = start_index + len(batch)

    has_more = next_index < len(data)

    return text, next_index, has_more


def extract_clipboard_content():
    clipboard_content = pyperclip.paste()

    try:
        data = json.loads(clipboard_content)
        print("данные похожи на json. Отлично")
        return data
    except json.JSONDecodeError as e:
        input("Текст в буфере не является валидным JSON попробуйте копировать ещё раз со всеми скобками.")
        return extract_clipboard_content()


def view_prompt(prompt: str, str_number_batch: str = "", prev_content: str = ""):
    console = Console()
    try:
        # view_warn_copy
        console.print("[red]Промпт для копировапния начинается после этих слов [/red] \n\n")
        # view base prompt
        print(prompt)
        if str_number_batch:
            console.print(f"\n\n [cyan]Порция {str_number_batch}[/cyan]")
        # console_continue_process
        console.input("[cyan]Отправте промпт в chatGPT, подождите ответ. "
                      "Cкопируйте и нажмите enter для извлечения из буфера обмена: [/cyan]")
        clipboard_content = extract_clipboard_content()
        # return answer
        if clipboard_content == prev_content:
            return view_prompt(prompt, str_number_batch + "[red] Буфер обмена тот же, замените[/red], ", prev_content)
        else:
            return clipboard_content
    except KeyboardInterrupt:
        warn_ctrl_c = "[red]Получил Ctrl+C для выкл консоли, выделите нормально потом копируйте[/red]"
        return view_prompt(prompt, str_number_batch + warn_ctrl_c, prev_content)


def semi_manual_processing(output_dir: Path, words_json_path: Path, lrc_path: Path, cards_per_batch: int = 10):
    # =========================================
    # First Prompt for gpt
    # =========================================
    first_gpt_prompt = create_unified_prompt(words_json_path, lrc_path)
    data_anki = view_prompt(first_gpt_prompt, "initialization gpt")

    # Создание файла в котором будет всё лежать
    path_anki = os.path.join(output_dir, "anki.json")
    with open(path_anki, "w", encoding="utf-8") as file:
        json.dump(data_anki, file)

    # =========================================
    # Process cards
    # =========================================

    config = load_config()
    prompt_cards_gen = config.get("prompt_cards_gen", "")
    lyrics = clean_lrc_text(read_lrc_file(lrc_path))
    total_cards = len(data_anki)
    prev_cards = ""

    for start in range(0, total_cards, cards_per_batch):
        batch = data_anki[start:start + cards_per_batch]

        cards_json = []

        for card in batch:
            cards_json.append({
                "lemma": card.get("lemma"),
                "sentence": card.get("sentence")
            })

        # демонстрация кол-ва записей
        current_batch = start // cards_per_batch + 1
        total_batches = (total_cards / cards_per_batch)
        str_number_batch = f'{current_batch}/{total_batches}'
        ready_prompt = replace_prompt_placeholder(
            "{song.lrc}",
            prompt_cards_gen,
            lyrics
        )
        ready_prompt = replace_prompt_placeholder(
            "{cards.json}",
            ready_prompt,
            str(cards_json)
        )
        cards = view_prompt(ready_prompt, str_number_batch, prev_cards)
        prev_cards = cards
        # update data_anki
        for i, new_card in enumerate(cards):
            data_anki[start + i].update(new_card)

    with open(path_anki, "w", encoding="utf-8") as file:
        json.dump(data_anki, file)

    return data_anki
