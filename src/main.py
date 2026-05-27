import time

from transcribe_audio import run_whisper
from generate_images import run_generate_images


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
    # WHISPER
    # =====================================

    print_block("RUNNING WHISPER")

    run_whisper()

    # =====================================
    # IMAGE GENERATION
    # =====================================

    print_block("RUNNING IMAGE GENERATION")

    run_generate_images()

    # =====================================

    total_time = time.time() - start_time

    print_block(
        f"PROJECT FINISHED | TOTAL TIME: {total_time:.2f} sec"
    )


if __name__ == "__main__":
    main()