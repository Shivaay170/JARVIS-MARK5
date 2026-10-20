import asyncio
import edge_tts
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
from jarvis.core.bus import bus

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
        for key, text in texts.items():
            path = f"assets/{key}.wav"
            communicate = edge_tts.Communicate(text, self.voice)
            await communicate.save(path)
            data, fs = sf.read(path)
            self.clips[key] = (data, fs)

    async def speak(self, text: str):
        # Simple sentence chunker
        sentences = text.replace('!', '.').replace('?', '.').split('.')
        for sentence in sentences:
            if not sentence.strip(): continue

            communicate = edge_tts.Communicate(sentence, self.voice)
            await communicate.save("temp_chunk.wav")
            data, fs = sf.read("temp_chunk.wav")

            self.current_playback = sd.play(data, fs)
            while self.current_playback:
                # Barge-in check (implemented via EventBus in main)
                await asyncio.sleep(0.1)
                if getattr(self, 'stop_playback', False):
                    sd.stop()
                    return

tts = TTSManager()
