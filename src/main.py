import time
from transcribe_audio import run_whisper
from generate_images import run_generate_images
from search_audio_and_lyric import resource_selection
from process_llm import semi_manual_processing
from audio_segmentation import slice_audio
from import_anki import import_to_anki
from pathlib import Path


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
    output_dir = audio_path.parent

    # =====================================
    # WHISPER
    # =====================================

    print_block("RUNNING WHISPER")

    words_json_path_str = run_whisper(audio_path, output_dir)

    # =====================================
    # Processing lyrics
    # =====================================

    print_block("Processing lyrics")

    gpt_output_data = semi_manual_processing(output_dir, Path(words_json_path_str), lrc_path)
    
    # =====================================
    # IMAGE GENERATION
    # =====================================

    print_block("RUNNING IMAGE GENERATION")

    run_generate_images(output_dir, gpt_output_data)

    # =====================================
    # Audio segmentation 
    # =====================================
    
    print_block("Audio segmentation")

    slice_audio(audio_path, output_dir, gpt_output_data)

    # =====================================
    # Anki connect
    # =====================================

    print_block("anki connect")

    import_to_anki(gpt_output_data, output_dir)

    # =====================================

    total_time = time.time() - start_time

    print_block(
        f"PROJECT FINISHED | TOTAL TIME: {total_time:.2f} sec"
    )


if __name__ == "__main__":
    main()