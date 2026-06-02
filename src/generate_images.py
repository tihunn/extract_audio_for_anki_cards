import json
import os
import torch

from diffusers import StableDiffusionXLPipeline

from config_loader import load_config


def run_generate_images(output_dir, gpt_output):

    print("=" * 60)
    print("START: IMAGE GENERATION")
    print("=" * 60)

    config = load_config()

    paths = config["paths"]
    settings = config["image_generation"]

    model_path = paths["model_path"]
    image_dir = output_dir / "images"

    width = settings["width"]
    height = settings["height"]

    steps = settings["steps"]
    cfg = settings["cfg"]

    seed = settings["seed"]

    negative_prompt = settings["negative_prompt"]

    os.makedirs(image_dir, exist_ok=True)

    print("Loading SDXL model...")

    pipe = StableDiffusionXLPipeline.from_single_file(
        model_path,
        torch_dtype=torch.float16,
        use_safetensors=True,
    )

    pipe = pipe.to("cuda")

    try:
        pipe.enable_xformers_memory_efficient_attention()
        print("xformers enabled")
    except Exception as e:
        print("xformers not enabled:", e)

    pipe.enable_vae_slicing()
    pipe.enable_vae_tiling()

    print(f"Loading prompts: {gpt_output}")

    with open(gpt_output, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)

    print(f"Loaded prompts: {len(prompts_data)}")

    generator = torch.Generator(device="cuda").manual_seed(seed)

    for index, item in enumerate(prompts_data):

        prompt = item.get("image_prompt", "").strip()
        word = item.get("word", "").strip()		

        if not prompt:
            print(f"Skipping empty prompt {word} #{index}")
            continue

        print("\n" + "-" * 60)
        print(f"Generating image #{word}")
        print(prompt)
        print("-" * 60)

        with torch.inference_mode():

            image = pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=steps,
                guidance_scale=cfg,
                generator=generator,
            ).images[0]

        filename = os.path.join(
            image_dir,
            f"{word}.png"
        )

        image.save(filename)

        print(f"Saved: {filename}")

    print("\nIMAGE GENERATION FINISHED")