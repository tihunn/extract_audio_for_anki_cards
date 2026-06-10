# extract_audio_for_anki_cards
Extract audio, transcription, text processing using deepseek or GPT, segmentation audio, create image, import all use anki connect for create anki cards. 

I installed the Python 3.11.9 virtual environment manually because that's the version DeepSeek recommended for Whisper. I'll check it later and create installation instructions.

Install ffmpeg

Linux:

sudo apt install ffmpeg

Windows:

download:
FFmpeg Builds https://www.gyan.dev/ffmpeg/builds/?utm_source=chatgpt.com

Install prodeject:

1. Insatall python
2. Check your cuda version (if you have it)
	nvcc --version
3. Go to the folder, launch the console and enter the code below 
	or run the bat file (if I make one)

python -m venv venv
venv\Scripts\activate
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu126
pip install -r requirements.txt