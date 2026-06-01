import time

from transcribe_audio import run_whisper
from generate_images import run_generate_images
from search_audio_and_lyric import resource_selection

def print_block(title):

    print("\n")
    print("#" * 80)
    print(title)
    print("#" * 80)
    print("\n")


def main():

    start_time = time.time()
	
    print_block("PROJECT START")
	
    # =====================================
    # Load audio
    # =====================================	
	
    audio_path, lrc_path = resource_selection()

    # =====================================
    # WHISPER
    # =====================================

    print_block("RUNNING WHISPER")

    run_whisper(audio_path)

    # =====================================
    # Processing lyrics
    # =====================================

    print_block("Processing lyrics")

    input("ждём файл вручную созданый в gpt")

    # =====================================
    # IMAGE GENERATION
    # =====================================

    print_block("RUNNING IMAGE GENERATION")

    run_generate_images()
	
    # =====================================
    # Anki connect
    # =====================================

    print_block("anki connect")

    print("пока нету")
	
    # =====================================

    total_time = time.time() - start_time

    print_block(
        f"PROJECT FINISHED | TOTAL TIME: {total_time:.2f} sec"
    )


if __name__ == "__main__":
    main()