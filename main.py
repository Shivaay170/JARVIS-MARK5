import sys
import asyncio
import time
import keyboard
import socket
import sounddevice as sd
import numpy as np
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from jarvis.core.bus import bus
from jarvis.brain.llm import llm
from jarvis.brain.agent import agent
from jarvis.brain.reflex import reflex
from jarvis.brain import commands as mem_commands
from jarvis.brain.learning import learner
from jarvis.senses.tts import tts
from jarvis.senses.stt import stt
from jarvis.senses.speaker import verifier, ENROLL_PHRASES
from jarvis.core.config import CONFIG
from jarvis.memory.store import store
from jarvis.ui.overlay import JarvisOverlay
import jarvis.tools.windows_tools   # registers tools
import jarvis.memory.memory_tools    # registers memory/profile tools

SAMPLE_RATE = 16000
RECORD_SECONDS = 3.5


def _voice_cfg():
    return CONFIG.get("settings", {}).get("voice", {})


def _record_audio(duration: float = RECORD_SECONDS, fs: int = SAMPLE_RATE) -> np.ndarray:
    """Record mono audio from the default input device."""
    audio = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


async def run_enroll():
    """`python main.py enroll` - record 10 phrases and save the voiceprint."""
    print("=" * 60)
    print("JARVIS SPEAKER ENROLLMENT")
    print("=" * 60)
    print(f"{len(ENROLL_PHRASES)} phrases. Speak clearly, one at a time.\n")

    def record() -> np.ndarray:
        print("  Recording... (speak now)")
        return _record_audio(3.0)

    def progress(msg: str):
        print(msg)

    ok = await asyncio.to_thread(verifier.enroll, record, ENROLL_PHRASES, progress)
    if ok:
        print("\nVoiceprint saved to data/voiceprint.npy.")
        print("JARVIS will now verify every voice command.")
        print("If the wrong voice gets through, raise settings.speaker.threshold in config.yaml.")
    else:
        print("\nEnrollment failed - no usable phrases captured. Try again.")
    store.flush()
    return 0 if ok else 1


class JarvisCore:
    def __init__(self):
        self.is_listening = False
        self.overlay = JarvisOverlay()
        self.trusted_text = False  # overlay text input is always trusted

    async def capture_and_process_speech(self):
        try:
            await bus.publish("state_change", "listening")
            await bus.publish("transcript", "Listening...")

            audio_data = await asyncio.to_thread(_record_audio)

            volume_norm = float(np.linalg.norm(audio_data) * np.sqrt(len(audio_data)))
            if volume_norm < 1.0:
                await bus.publish("state_change", "idle")
                self.is_listening = False
                return

            await bus.publish("state_change", "thinking")
            await bus.publish("transcript", "Transcribing...")

            text = await stt.transcribe(audio_data)
            self.is_listening = False

            if not text:
                await bus.publish("state_change", "idle")
                await bus.publish("transcript", "Ready for your command, sir.")
                return

            # Speaker verification: every voice command is checked.
            if verifier.enabled and verifier.is_enrolled():
                score = verifier.similarity(audio_data)
                threshold = verifier.threshold
                if score < threshold:
                    # On failure: ignore silently, log only.
                    print(f"Speaker rejected (score={score:.3f} < {threshold:.2f}) - ignored.")
                    await bus.publish("state_change", "idle")
                    return

            await self.handle_input(text)

        except Exception as e:
            print(f"Speech processing error: {e}")
            self.is_listening = False
            await bus.publish("state_change", "idle")

    async def handle_input(self, text: str, trusted: bool = True):
        if not text or not text.strip():
            return
        text = text.strip()

        # 0. Memory commands (no LLM call needed)
        cmd = mem_commands.match(text)
        if cmd:
            result = mem_commands.run(cmd[0], cmd[1])
            await bus.publish("response", result)
            await bus.publish("state_change", "speaking")
            await tts.speak(result)
            await bus.publish("state_change", "idle")
            return

        # 1. Reflex Layer (no LLM call needed)
        reflex_hit = reflex.match(text)
        if reflex_hit:
            reflex_action, reflex_args = reflex_hit
            await bus.publish("state_change", "thinking")
            await bus.publish("transcript", text)
            tool_def = jarvis.tools.windows_tools.registry.tools.get(reflex_action)
            if tool_def:
                res = await agent._execute_tool(tool_def["func"], reflex_args)
            else:
                res = f"Executing {reflex_action}, sir."
            await bus.publish("response", str(res))
            await bus.publish("state_change", "speaking")
            await tts.speak(str(res))
            await bus.publish("state_change", "idle")
            return

        # 2. Agent Loop
        await bus.publish("state_change", "thinking")
        await bus.publish("transcript", text)

        response = await agent.run(text)

        await bus.publish("response", response)
        await bus.publish("state_change", "speaking")
        await tts.speak(response)
        await bus.publish("state_change", "idle")

        # 3. Background maintenance: batched, one call per session/day.
        asyncio.create_task(self._background_maintenance())

    async def _background_maintenance(self):
        try:
            await learner.maybe_extract_facts()
            await learner.maybe_rewrite_profile()
        except Exception as e:
            print(f"Background maintenance error: {e}")
        finally:
            store.flush()

    def toggle_listen(self):
        self.is_listening = not self.is_listening
        if self.overlay.isHidden():
            self.overlay.show()
        self.overlay.raise_()
        self.overlay.activateWindow()
        if self.is_listening:
            asyncio.get_event_loop().create_task(self.capture_and_process_speech())


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "enroll":
        return asyncio.run(run_enroll())

    app = QApplication([])
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    core = JarvisCore()
    loop.run_until_complete(tts.preload_clips())

    # Overlay text input is always trusted.
    core.overlay.text_submitted.connect(
        lambda t: loop.create_task(core.handle_input(t, trusted=True))
    )

    bus.subscribe("state_change", lambda d: QTimer.singleShot(0, lambda: core.overlay.handle_event("state_change", str(d))))
    bus.subscribe("transcript", lambda d: QTimer.singleShot(0, lambda: core.overlay.handle_event("transcript", str(d))))
    bus.subscribe("response", lambda d: QTimer.singleShot(0, lambda: core.overlay.handle_event("response", str(d))))

    async def socket_listener():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 65432))
        server.listen(1)
        server.setblocking(False)
        while True:
            try:
                conn, addr = await loop.sock_accept(server)
                data = await loop.sock_recv(conn, 1024)
                if data == b"activate":
                    core.toggle_listen()
                conn.close()
            except Exception:
                await asyncio.sleep(0.1)

    keyboard.add_hotkey("f9", lambda: QTimer.singleShot(0, core.toggle_listen))
    loop.create_task(socket_listener())

    timer = QTimer()

    def step_asyncio():
        loop.stop()
        loop.run_forever()

    timer.timeout.connect(step_asyncio)
    timer.start(10)

    core.overlay.show()
    core.overlay.raise_()
    core.overlay.activateWindow()

    if verifier.is_enrolled():
        print("JARVIS Online. Voiceprint loaded - voice commands will be verified.")
    else:
        print("JARVIS Online. No voiceprint: run `python main.py enroll` to enable verification.")
    app.exec()
    store.flush()


if __name__ == "__main__":
    main()
