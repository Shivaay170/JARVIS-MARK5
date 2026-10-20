import asyncio
import time
import keyboard
from faster_whisper import WhisperModel
from jarvis.core.bus import bus
from jarvis.brain.llm import llm
from jarvis.senses.tts import tts
from jarvis.core.config import CONFIG

class JarvisCore:
    def __init__(self):
        self.model = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.is_listening = False

    async def handle_input(self, text: str):
        start_time = time.time()
        print(f"User: {text}")

        # Brain
        full_response = ""
        tt_first_audio = None

        async def process_llm():
            nonlocal tt_first_audio
            async for chunk in llm.generate(text):
                nonlocal full_response
                full_response += chunk
                # In a real implementation, we'd chunk sentences here and stream to TTS

        await process_llm()

        # Simple output for now
        print(f"JARVIS: {full_response}")
        await tts.speak(full_response)

        end_time = time.time()
        print(f"Total Latency: {end_time - start_time:.3f}s")

    def toggle_listen(self):
        self.is_listening = not self.is_listening
        print(f"Listening: {self.is_listening}")

async def main():
    core = JarvisCore()
    await tts.preload_clips()

    keyboard.add_hotkey('f9', core.toggle_listen)

    print("JARVIS Online. Press F9 to talk or type text.")
    while True:
        if not core.is_listening:
            user_text = await asyncio.to_thread(input, "Text input: ")
            await core.handle_input(user_text)
        else:
            # Simulating VAD/STT cycle
            print("Capturing audio...")
            await asyncio.sleep(2) # Mock audio capture
            await core.handle_input("Hello JARVIS")
            core.is_listening = False

if __name__ == "__main__":
    asyncio.run(main())
