import os
import re
import shutil
import subprocess
from pathlib import Path

import syncedlyrics
from mutagen import File
from rich.console import Console

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


def sanitize_filename(name: str):
    return re.sub(r'[\\/*?:"<>|]', "", name)


def download_youtube_audio(url: str):
    console.print(f"[cyan]Скачивание аудио:[/cyan] {url}")

    output_template = str(OUTPUT_DIR / "%(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format",
        "mp3",
        "-o",
        output_template,
        url,
    ]

    subprocess.run(cmd, check=True)

    latest = max(
        OUTPUT_DIR.glob("*.mp3"),
        key=os.path.getctime
    )

    console.print(f"[green]Аудио скачано:[/green] {latest}")

    return latest


def find_local_audio():
    for file in INPUT_DIR.iterdir():
        if file.suffix.lower() in SUPPORTED_AUDIO:
            console.print(f"[green]Найден локальный файл:[/green] {file}")
            return file

    return None


def extract_metadata(audio_path: Path):
    audio = File(audio_path)

    title = None
    artist = None

    if audio:
        title = audio.get("TIT2")
        artist = audio.get("TPE1")

        if isinstance(title, list):
            title = str(title[0])

        if isinstance(artist, list):
            artist = str(artist[0])

    if not title:
        title = audio_path.stem

    if not artist:
        artist = ""

    return str(title), str(artist)


def copy_to_output(audio_path: Path):
    destination = OUTPUT_DIR / audio_path.name

    if audio_path.resolve() != destination.resolve():
        shutil.copy(audio_path, destination)

    return destination


def search_lyrics(title: str, artist: str):
    query = f"{title} {artist}".strip()

    console.print(f"[yellow]Поиск lyrics:[/yellow] {query}")

    # Сначала пытаемся synced lyrics
    try:
        lrc = syncedlyrics.search(
            query,
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
            query,
            providers=LYRICS_PROVIDERS,
            plain_only=True,
        )

        if lrc:
            console.print("[yellow]Найдены plain lyrics[/yellow]")
            return lrc

    except Exception as e:
        console.print(f"[red]Ошибка plain lyrics:[/red] {e}")

    return None


def save_lyrics(audio_path: Path, lyrics: str):
    lrc_path = OUTPUT_DIR / f"{audio_path.stem}.lrc"

    with open(lrc_path, "w", encoding="utf-8") as f:
        f.write(lyrics)

    console.print(f"[green]Lyrics сохранены:[/green] {lrc_path}")


def main():
    console.print("[bold cyan]=== Japanese Song Fetcher ===[/bold cyan]")

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

            audio_path = copy_to_output(audio_path)

        elif choice == "2":
            url = input("YouTube URL: ").strip()
            audio_path = download_youtube_audio(url)

        elif choice == "3":
            query = input("Название песни / artist: ").strip()

            console.print(
                "[yellow]Используйте YouTube search через yt-dlp...[/yellow]"
            )

            output_template = str(OUTPUT_DIR / "%(title)s.%(ext)s")

            cmd = [
                "yt-dlp",
                f"ytsearch1:{query}",
                "-x",
                "--audio-format",
                "mp3",
                "-o",
                output_template,
            ]

            subprocess.run(cmd, check=True)

            audio_path = max(
                OUTPUT_DIR.glob("*.mp3"),
                key=os.path.getctime
            )

        else:
            console.print("[red]Неверный выбор[/red]")
            return

        title, artist = extract_metadata(audio_path)

        console.print(f"\n[cyan]Title:[/cyan] {title}")
        console.print(f"[cyan]Artist:[/cyan] {artist}")

        lyrics = search_lyrics(title, artist)

        if lyrics:
            save_lyrics(audio_path, lyrics)
        else:
            console.print("[red]Lyrics не найдены[/red]")

        console.print("\n[bold green]Готово[/bold green]")

    except KeyboardInterrupt:
        console.print("\n[red]Остановлено пользователем[/red]")

    except Exception as e:
        console.print(f"[bold red]Ошибка:[/bold red] {e}")


if __name__ == "__main__":
    main()