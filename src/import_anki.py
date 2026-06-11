from pathlib import Path
import base64
import requests


ANKI_URL = "http://localhost:8765"

def cutter_str(str):
    return str[:4] + "-" + str[-4:] if len(str) > 8 else str


def anki(action: str, **params):
    response = requests.post(
        ANKI_URL,
        json={
            "action": action,
            "version": 6,
            "params": params
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("error"):
        raise RuntimeError(
            f"AnkiConnect error: {data['error']}"
        )

    print("post action: " + action)

    return data["result"]


def upload_media(
    local_path: Path,
    target_filename: str
) -> str | None:

    if not local_path.exists():
        return None

    with open(local_path, "rb") as f:
        encoded = base64.b64encode(
            f.read()
        ).decode("utf-8")
		
    anki(
        "storeMediaFile",
        filename=target_filename,
        data=encoded
    )
    
    return target_filename


def ensure_deck(deck_name: str):
    decks = anki("deckNames")

    if deck_name not in decks:
        anki(
            "createDeck",
            deck=deck_name
        )


def ensure_model(model_name = "Japanese Song Vocabulary by tihun"):

    models = anki("modelNames")

    if model_name in models:
        return model_name

    css = r"""
.card {
    font-family: "Noto Sans JP", sans-serif;
    text-align: center;
    padding: 16px;
    max-width: 800px;
    margin: 0 auto;
}
.word {
    font-size: clamp(32px, 8vw, 56px);
    font-weight: 600;
    margin: 12px 0;
    line-height: 1.2;
    word-break: keep-all;
}

ruby {
    font-size: clamp(22px, 5vw, 36px);
}

ruby rt {
    font-size: 0.45em;
    color: #888;
}

.translation {
    margin-top: 15px;
    font-size: 22px;
}

.image img {
    width: min(320px, 90vw);
    height: auto;
    border-radius: 8px;
}

.sentence {
    margin-top: 20px;
    font-size: clamp(18px, 4vw, 24px);
    line-height: 1.5;
}

.sentence-ru {
    margin-top: 10px;
    color: #888;
    font-size: clamp(14px, 3vw, 18px);
    line-height: 1.4;
}

.hidden-reading {
    display: none;
}
"""

    front = r"""
<div class="word">
    {{word}}{{audio_word}}
</div>


"""

    back = r"""
{{FrontSide}}

<hr>

<div>
    <ruby>
        {{lemma}}
        <rt>{{furigana}}</rt>
    </ruby>
</div>

<div class="translation">
    {{translation}}
</div>

<div class="image">
    {{image}}
</div>

<div class="sentence">
    {{sentence}}{{audio_sentence}}
</div>

<div class="sentence-ru">
    {{sentence_ru}}
</div>



<div class="hidden-reading">
    {{reading}}
</div>
"""

    anki(
        "createModel",
        modelName=model_name,
        inOrderFields=[
            "word",
            "lemma",
            "reading",
            "furigana",
            "part_of_speech",
            "translation",
            "sentence",
            "sentence_ru",
            "image",
            "audio_word",
            "audio_sentence",
        ],
        css=css,
        cardTemplates=[
            {
                "Name": f"Vocabulary by tihun",
                "Front": front,
                "Back": back,
            }
        ],
    )

    return model_name


def import_to_anki(
    gpt_output_data: list[dict],
    output_dir: Path,
):
    """
    Создаёт модель, доску anki и Импортирует все медиа

    Parameters
    ----------
    gpt_output_data: list[dict] 
        Распакованые данные из json из после обработки gpt
    output_dir: Path
        Папка с файлами всех результатов обработки предыдущих скриптов
    """

    deck_name = output_dir.stem
    words_dir = output_dir / "words"
    sentences_dir = output_dir / "sentences"
    images_dir = output_dir / "images"

    print(f"Loaded {len(gpt_output_data)} cards")

    anki("version")

    ensure_deck(deck_name)

    model_name = ensure_model()

    song_name = output_dir.stem

    created = 0
    failed = 0

    for idx, item in enumerate(gpt_output_data, start=1):

        word = item["word"]
        sentence = item["sentence"]

        image_path = images_dir / f"{word}.png"
        word_audio_path = words_dir / f"{word}.mp3"
        sentence_audio_path = (sentences_dir / f"{sentence}.mp3")

        image_media_name = (f"{cutter_str(song_name)}_{cutter_str(word)}.png")
        word_media_name = (f"{cutter_str(song_name)}_{cutter_str(word)}.mp3")
        sentence_media_name = (f"{cutter_str(song_name)}_{cutter_str(sentence)}.mp3")

        image_file = upload_media(image_path, image_media_name)

        word_audio_file = upload_media(word_audio_path, word_media_name)

        sentence_audio_file = upload_media(sentence_audio_path, sentence_media_name)

        note = {
            "deckName": deck_name,
            "modelName": model_name,
            "fields": {
                "word": item.get("word", ""),
                "lemma": item.get("lemma", ""),
                "reading": item.get("reading", ""),
                "furigana": item.get("furigana", ""),
                "part_of_speech": item.get(
                    "part_of_speech",
                    ""
                ),
                "translation": item.get(
                    "translation",
                    ""
                ),
                "sentence": item.get(
                    "sentence",
                    ""
                ),
                "sentence_ru": item.get(
                    "sentence_ru",
                    ""
                ),
                "image": (
                    f'<img src="{image_file}">'
                    if image_file
                    else ""
                ),
                "audio_word": (
                    f"[sound:{word_audio_file}]"
                    if word_audio_file
                    else ""
                ),
                "audio_sentence": (
                    f"[sound:{sentence_audio_file}]"
                    if sentence_audio_file
                    else ""
                ),
            },
            "tags": [
                "song",
                song_name
            ]
        }

        try:
            anki(
                "addNote",
                note=note
            )

            created += 1

            print(
                f"[{created}] "
                f"{word}"
            )

        except Exception as e:

            failed += 1

            print(
                f"[ERROR] {word}: {e}"
            )

    print()
    print(f"Created: {created}")
    print(f"Failed : {failed}")