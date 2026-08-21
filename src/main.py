import time
from transcribe_audio import run_whisper
from generate_images import run_generate_images
from search_audio_and_lyric import resource_selection
from process_llm import semi_manual_processing
from audio_segmentation import slice_audio
from import_anki import import_to_anki
from import_sentence import import_sentences_to_anki
from import_only_sentence import create_anki_deck
from pathlib import Path
from rich.console import Console
import json


def print_block(title):
    print("\n")
    print("#" * 80)
    print(title)
    print("#" * 80)
    print("\n")


console = Console()


def select_project_folder() -> Path | None:
    """
    Показывает список проектов из папки output
    и возвращает Path выбранной папки.

    Returns:
        Path | None
    """

    output_dir = Path("output")

    if not output_dir.exists():
        console.print("[red]Папка output не найдена[/red]")
        return None

    projects = sorted(
        [p for p in output_dir.iterdir() if p.is_dir()]
    )

    if not projects:
        console.print("[red]В output нет проектов[/red]")
        return None

    console.print("\n[bold cyan]Доступные проекты:[/bold cyan]")

    for i, project in enumerate(projects, start=1):
        console.print(
            f"[green]{i}.[/green] {project.name}"
        )

    while True:
        choice = input("\nВыберите проект: ").strip()

        try:
            index = int(choice) - 1

            if 0 <= index < len(projects):
                selected = projects[index]

                console.print(
                    f"\n[green]Выбран проект:[/green] {selected.name}"
                )

                return selected.resolve()

        except ValueError:
            pass

        console.print("[red]Некорректный выбор[/red]")


def find_file(folder, filename):
    """
    Поиск файла в папке.

    Args:
        folder: путь к папке (Path или str)
        filename: имя файла (str или Path)

    Returns:
        Path или сообщение об ошибке
    """
    put = Path(folder) / filename
    return put if put.exists() else f"Файл {filename} не найден"


def search_first_file_by_ext(folder: Path, extension: str = "*.lrc"):
    """
    Поиск .lrc файла в папке.

    Args:
        folder: путь к папке (Path)

    Returns:
        Path первого найденного .lrc файла или сообщение об ошибке
    """
    lrc_files = list(folder.glob(extension))

    if not lrc_files:
        return f"Файлы .lrc не найдены в {folder}"

    # Если нашли несколько, возвращаем первый
    return lrc_files[0]


def get_gpt_output_data(output_dir, name_data: str = "anki.json"):
    path_anki = output_dir / name_data
    with open(path_anki, "r", encoding="utf-8") as file:
        return json.load(file)


from pathlib import Path


def find_audio_file(folder: Path) -> Path:
    """
    Ищет первый аудиофайл в папке.

    Args:
        folder: путь к папке

    Returns:
        Path к найденному аудиофайлу или None
    """
    audio_extensions = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac", ".wma", ".opus", ".aiff", ".alac"}

    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in audio_extensions:
            return file

    raise FileNotFoundError(f"Аудиофайл не найден в {folder}")


def choice_pipeline():
    print("\n1. Полный запуск для слов")
    print("11. Полный запуск только для предложения")
    print("\n Запустить отдельные части конвеера")
    print("2. Whisper")
    print("3. Полуавтоматическая обработка текста")
    print("4. Генерация картинок")
    print("5. Нарезка аудио")
    print("6. Импорт через ankiConnect")
    print("7. Импорт Предложений через ankiConnect из файла слов")
    print("8. Полуавтоматическая обработка предложений")
    print("9. нарезка аудио только предложений")
    print("10. Импорт Предложений через ankiConnect 2")

    mode = input("Выбор: ").strip()

    if mode == "1":
        run_full_pipeline()

    elif mode == "11":
        run_full_pipeline(False)

    elif mode == "2":
        output_dir = select_project_folder()
        audio_path = find_audio_file(output_dir)
        run_whisper(audio_path, output_dir)

    elif mode == "3":
        output_dir = select_project_folder()
        words_json_path = find_file(output_dir, "words_by_whisper.json")
        lrc_path = search_first_file_by_ext(output_dir, "*.lrc")
        semi_manual_processing(output_dir, lrc_path, words_json_path)

    elif mode == "4":
        output_dir = select_project_folder()
        run_generate_images(output_dir, get_gpt_output_data(output_dir))

    elif mode == "5":
        output_dir = select_project_folder()
        audio_path = find_audio_file(output_dir)
        slice_audio(audio_path, output_dir, get_gpt_output_data(output_dir))

    elif mode == "6":
        output_dir = select_project_folder()
        import_to_anki(get_gpt_output_data(output_dir), output_dir)

    elif mode == "7":
        output_dir = select_project_folder()
        import_sentences_to_anki(output_dir, get_gpt_output_data(output_dir))

    elif mode == "8":
        output_dir = select_project_folder()
        lrc_path = search_first_file_by_ext(output_dir, "*.lrc")
        semi_manual_processing(output_dir, lrc_path, is_sentence=True)

    elif mode == "9":
        output_dir = select_project_folder()
        audio_path = find_audio_file(output_dir)
        slice_audio(audio_path,
                    output_dir,
                    get_gpt_output_data(output_dir, "anki_sentences.json"),
                    False)

    elif mode == "10":
        output_dir = select_project_folder()
        create_anki_deck(output_dir, get_gpt_output_data(output_dir, "anki_sentences.json"), ankiconnect=True)

    else:
        print("Ввели что-то не то, перезапущу")
        choice_pipeline()


def run_full_pipeline(is_words: bool = True, is_ankiconnect: bool = True):

    start_time = time.time()

    print_block("PROJECT START")

    # =====================================
    # Load audio
    # =====================================	

    audio_path, lrc_path = resource_selection()
    output_dir = audio_path.parent

    # =====================================
    # WHISPER
    # =====================================
    if is_words:
        print_block("RUNNING WHISPER")

        words_json_path_str, segments_json_path, full_text_with_breaks = run_whisper(audio_path, output_dir)
        words_json_path = Path(words_json_path_str)
    else:
        words_json_path = None
    # =====================================
    # Processing lyrics
    # =====================================

    print_block("Processing lyrics")

    gpt_output_data = semi_manual_processing(output_dir, lrc_path, words_json_path, is_sentence=not is_words)
    
    # =====================================
    # IMAGE GENERATION
    # =====================================
    if is_words:
        print_block("RUNNING IMAGE GENERATION")

        run_generate_images(output_dir, gpt_output_data)

    # =====================================
    # Audio segmentation 
    # =====================================
    
    print_block("Audio segmentation")

    slice_audio(audio_path, output_dir, gpt_output_data, slice_words=is_words)

    # =====================================
    # Anki connect
    # =====================================

    print_block("anki connect")
    if is_words:
        import_to_anki(gpt_output_data, output_dir)
    else:
        create_anki_deck(output_dir, gpt_output_data, ankiconnect=is_ankiconnect)
    # =====================================

    total_time = time.time() - start_time

    print_block(
        f"PROJECT FINISHED | TOTAL TIME: {total_time:.2f} sec"
    )


if __name__ == "__main__":
    choice_pipeline()
