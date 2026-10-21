import asyncio
import edge_tts
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
from jarvis.core.bus import bus
from jarvis.core.config import DATA_DIR, path as base_path

CHUNK_PATH = os.path.join(DATA_DIR, "temp_chunk.wav")
ASSETS_DIR = base_path("assets")

class TTSManager:
    def __init__(self):
        self.voice = "en-GB-RyanNeural"
        self.current_playback = None
        self.clips = {}

    async def preload_clips(self):
        texts = {
            "yes": "Yes, sir?",
            "on_it": "On it, sir.",
            "moment": "One moment, sir.",
            "done": "Done.",
            "init": "Initializing, sir."
        }
        os.makedirs(ASSETS_DIR, exist_ok=True)
        for key, text in texts.items():
            path = os.path.join(ASSETS_DIR, f"{key}.wav")
            if not os.path.exists(path):
                try:
                    communicate = edge_tts.Communicate(text, self.voice)
                    await communicate.save(path)
                except Exception as e:
                    print(f"TTS preload error for {key}: {e}")
                    continue
            if os.path.exists(path):
                data, fs = sf.read(path)
                self.clips[key] = (data, fs)

    async def speak(self, text: str):
        # Defence in depth: reasoning must never be spoken.
        for tag in ("<think>", "</think>", "<reasoning>", "</reasoning>",
                    "<analysis>", "</analysis>", "<|channel|>", "<|end|>"):
            text = text.replace(tag, "")
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence: continue

            try:
                communicate = edge_tts.Communicate(sentence, self.voice)
                await communicate.save(CHUNK_PATH)
                data, fs = sf.read(CHUNK_PATH)

                sd.play(data, fs)
                duration = len(data) / fs
                start_t = asyncio.get_event_loop().time()
                while asyncio.get_event_loop().time() - start_t < duration:
                    if getattr(self, 'stop_playback', False):
                        sd.stop()
                        return
                    await asyncio.sleep(0.05)
            except Exception as e:
                print(f"TTS Speak Error: {e}")

tts = TTSManager()
