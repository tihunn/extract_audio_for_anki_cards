from pathlib import Path, WindowsPath
from pytubefix import Search
from pytubefix import YouTube
from pytubefix.cli import on_progress
from rich.table import Table
from rich.prompt import Prompt
from rich.console import Console
from rich import box
import syncedlyrics
import os
import shutil

import logging

# =========================
# CONFIG
# =========================

console = Console()
INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")

OUTPUT_DIR.mkdir(exist_ok=True)
INPUT_DIR.mkdir(exist_ok=True)

# Порядок источников lyrics
LYRICS_PROVIDERS = [
    "NetEase",
    "Musixmatch",
    "LRCLib",
    "Megalobiz",
    "Genius",
]

SUPPORTED_AUDIO = [
    ".mp3",
    ".flac",
    ".m4a",
    ".wav",
    ".ogg",
]

# =========================================================
# YOUTUBE DOWNLOAD
# =========================================================

def download_youtube_audio(url: str) -> str:
    yt = YouTube(
        url,
        on_progress_callback=on_progress
    )

    stream = yt.streams.get_audio_only()

    path = stream.download(output_path=str(INPUT_DIR))

    print(f"\nСкачано: {path}")

    return path

	
def search_youtube_video(query: str, limit: int = 6) -> str:
    """
    Ищет видео на YouTube через pytubefix.
    
    Args:
        query: поисковый запрос
        limit: сколько результатов показать

    Returns:
        str: выбранный YouTube URL
    """

    console.print(f"\n[bold cyan]Поиск:[/bold cyan] {query}")

    search = Search(query)

    videos = search.videos[:limit]

    if not videos:
        raise ValueError("Ничего не найдено")

    table = Table(
        title="Результаты поиска YouTube",
        box=box.ROUNDED,
        show_lines=True
    )

    table.add_column("#", style="cyan", width=4)
    table.add_column("Название", style="white")
    table.add_column("Длительность", style="green", width=12)
    table.add_column("Автор", style="magenta")

    for idx, video in enumerate(videos, start=1):

        minutes = video.length // 60
        seconds = video.length % 60

        duration = f"{minutes}:{seconds:02d}"

        author = getattr(video, "author", "Unknown")

        table.add_row(
            str(idx),
            video.title,
            duration,
            author
        )

    console.print(table)

    while True:
        choice = Prompt.ask(
            "\nВыбери номер видео",
            default="1"
        )

        if choice.isdigit():
            choice_num = int(choice)

            if 1 <= choice_num <= len(videos):
                selected = videos[choice_num - 1]

                console.print(
                    f"\n[bold green]Выбрано:[/bold green] {selected.title}"
                )

                console.print(
                    f"[blue]{selected.watch_url}[/blue]"
                )

                return selected.watch_url

        console.print("[red]Некорректный номер[/red]")

# =========================================================
# LOCAL AUDIO
# =========================================================	

def find_local_audio():

    files = []

    for file in INPUT_DIR.iterdir():

        if (
            file.suffix.lower()
            in SUPPORTED_AUDIO
        ):
            files.append(file)

    if not files:
        return None

    console.print(
        "\n[bold cyan]Audio files:[/bold cyan]"
    )

    for i, file in enumerate(files, 1):

        console.print(
            f"[green]{i}.[/green] "
            f"{file.name}"
        )

    choice = input(
        "\nSelect file: "
    ).strip()

    try:

        index = int(choice) - 1

        selected = files[index]

        console.print(
            f"\n[green]Selected:[/green] "
            f"{selected.name}"
        )

        return selected

    except Exception:

        return None


# =========================================================
# LYRICS SEARCH
# =========================================================

def search_lyrics(audio_name: str):
    # 1. Настраиваем корневой логгер, чтобы видеть сообщения уровня INFO и DEBUG
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    console.print(f"[yellow]Поиск lyrics:[/yellow] {audio_name}")

    # Сначала пытаемся synced lyrics
    try:
        lrc = syncedlyrics.search(
            audio_name,
            providers=LYRICS_PROVIDERS,
            enhanced=True,
        )

        if lrc:
            console.print("[green]Найдены synced lyrics[/green]")
            return lrc

    except Exception as e:
        console.print(f"[red]Ошибка synced lyrics:[/red] {e}")

    # fallback plain lyrics
    try:
        lrc = syncedlyrics.search(
            audio_name,
            providers=LYRICS_PROVIDERS,
            plain_only=True,
        )

        if lrc:
            console.print("[yellow]Найдены plain lyrics[/yellow]")
            return lrc

    except Exception as e:
        console.print(f"[red]Ошибка plain lyrics:[/red] {e}")

    return None

# =========================================================
# SAVE LYRICS
# =========================================================

def save_lyrics(lyrics_name: str, lyrics: str, audio_folder):
    lrc_path = audio_folder / f"{lyrics_name}.lrc"

    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lyrics)
    return lrc_path

    console.print(f"[green]Lyrics сохранены:[/green] {lrc_path}")

# =========================================================
# create_music_folder
# =========================================================

def create_music_folder(audio_path):
    """
    Создает папку с названием музыки и копирует/перемещает файлы
    
    Args:
        audio_path: путь к аудиофайлу (объект WindowsPath или str)
        
        source_path: исходный путь для копирования (только для локальных файлов)
    
    Returns:
        новый путь к файлу в созданной папке
    """
    # Получаем имя музыки (без расширения)
    music_name = audio_path.stem if hasattr(audio_path, 'stem') else Path(audio_path).stem
    
    # Создаем путь к новой папке (output/{название_музыки}/)
    output_dir = Path("output") / music_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Определяем новый путь для аудиофайла
    original_extension = audio_path.suffix if hasattr(audio_path, 'suffix') else Path(audio_path).suffix
    new_audio_path = output_dir / f"{music_name}{original_extension}"
    

        # Для скачанных файлов - перемещаем в новую папку
    shutil.move(str(audio_path), str(new_audio_path))
    console.print(f"[green]Файл перемещен в {output_dir}[/green]")
    
    return new_audio_path	
	
# =========================================================
# MAIN
# =========================================================

def resource_selection():
    console.print("\n [bold cyan]=== Japanese Song Fetcher ===[/bold cyan]")

    console.print("\n1. Использовать локальный файл")
    console.print("2. Скачать с YouTube")
    console.print("3. Автопоиск\n")

    choice = input("Выбор: ").strip()

    audio_path = None

    try:
        if choice == "1":
            audio_path = find_local_audio()
            
            if not audio_path:
                console.print("[red]В input/ нет аудиофайлов[/red]")
                return

        elif choice == "2":
            url = input("YouTube URL: ").strip()
            path_str = download_youtube_audio(url)
            audio_path = WindowsPath(path_str)
            
        elif choice == "3":
            name_song = input("name song: ").strip()
            url = search_youtube_video(name_song)
            path_str = download_youtube_audio(url)
            audio_path = WindowsPath(path_str)

        else:
            console.print("[red]Неверный выбор[/red]")
            return

        audio_path = create_music_folder(audio_path)
			
        def search_and_save_lyric(audio_folder, audio_name):
            if not audio_name:
                return None
			
            lyrics = search_lyrics(audio_name)
            if lyrics:
                return save_lyrics(audio_name, lyrics, audio_folder)
            else:
                console.print("[red]Lyrics не найдены[/red]")
                audio_name = input("\nПопробуйте вести название вручную, или оставьте пустую строку: ").strip()
                search_and_save_lyric(audio_folder, audio_name)
				
        audio_folder = audio_path.parent
        lrc_path = search_and_save_lyric(audio_folder, audio_path.stem)
        console.print("\n[bold green]Готово[/bold green]")
		
        return audio_path, lrc_path 
		
    except KeyboardInterrupt:
        console.print("\n[red]Остановлено пользователем[/red]")

    except Exception as e:
        console.print(f"[bold red]Ошибка:[/bold red] {e}")


if __name__ == "__main__":
    resource_selection()