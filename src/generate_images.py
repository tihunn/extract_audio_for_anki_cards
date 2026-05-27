import json
import os
import torch

from diffusers import StableDiffusionXLPipeline
from safetensors.torch import load_file


MODEL_PATH = "input/Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors"
PROMPTS_FILE = "input/anki_deck1_unique_words.json"
OUTPUT_DIR = "output"

# =========================
# НАСТРОЙКИ ГЕНЕРАЦИИ
# =========================

WIDTH = 1024
HEIGHT = 1024

STEPS = 30
CFG = 7.0

NEGATIVE_PROMPT = (
    "worst quality, low quality, blurry, bad anatomy, "
    "deformed, distorted, watermark, text"
)

# =========================

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("Loading SDXL model...")

pipe = StableDiffusionXLPipeline.from_single_file(
    MODEL_PATH,
    torch_dtype=torch.float16,
    use_safetensors=True,
)

pipe = pipe.to("cuda")

# xformers
try:
    pipe.enable_xformers_memory_efficient_attention()
    print("xformers enabled")
except Exception as e:
    print("xformers not enabled:", e)

# memory optimizations
pipe.enable_vae_slicing()
pipe.enable_vae_tiling()

# =========================
# ЧТЕНИЕ JSON
# =========================

with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
    prompts_data = json.load(f)

print(f"Loaded prompts: {len(prompts_data)}")

# =========================
# ГЕНЕРАЦИЯ
# =========================

for index, item in enumerate(prompts_data):

    prompt = item.get("image_prompt", "").strip()

    if not prompt:
        print(f"Skipping empty prompt #{index}")
        continue

    print(f"\nGenerating #{index}")
    print(prompt)

    with torch.inference_mode():

        image = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            width=WIDTH,
            height=HEIGHT,
            num_inference_steps=STEPS,
            guidance_scale=CFG,
        ).images[0]

    filename = os.path.join(
        OUTPUT_DIR,
        f"image_{index:04d}.png"
    )

    image.save(filename)

    print(f"Saved: {filename}")

print("\nDone.")