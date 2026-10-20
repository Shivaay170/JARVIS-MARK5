import asyncio
import time
import keyboard
import socket
from PyQt6.QtWidgets import QApplication
from faster_whisper import WhisperModel
from jarvis.core.bus import bus
from jarvis.brain.llm import llm
from jarvis.senses.tts import tts
from jarvis.core.config import CONFIG
from jarvis.ui.overlay import JarvisOverlay

class JarvisCore:
    def __init__(self):
        self.model = WhisperModel("base.en", device="cpu", compute_type="int8")
        self.is_listening = False
        self.overlay = JarvisOverlay()
        self.overlay.setGeometry(
            QApplication.primaryScreen().availableGeometry().width() - 400,
            QApplication.primaryScreen().availableGeometry().height() - 260,
            380, 240
        )

    async def handle_input(self, text: str):
        # ... previous implementation ...
        await bus.publish("state_change", "thinking")
        await bus.publish("transcript", text)

        full_response = ""
        async for chunk in llm.generate(text):
            full_response += chunk

        await bus.publish("response", full_response)
        await bus.publish("state_change", "speaking")
        await tts.speak(full_response)
        await bus.publish("state_change", "idle")

    def toggle_listen(self):
        self.is_listening = not self.is_listening
        self.overlay.show()

async def main():
    app = QApplication([])
    core = JarvisCore()
    await tts.preload_clips()

    # Socket listener for launcher
    async def socket_listener():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(('127.0.0.1', 65432))
        server.listen(1)
        server.setblocking(False)
        loop = asyncio.get_event_loop()
        while True:
            try:
                conn, addr = await loop.sock_accept(server)
                data = await loop.sock_recv(conn, 1024)
                if data == b"activate":
                    core.toggle_listen()
                conn.close()
            except Exception:
                await asyncio.sleep(0.1)

    keyboard.add_hotkey('f9', core.toggle_listen)

    asyncio.create_task(socket_listener())

    print("JARVIS Online.")
    # Integrate PyQt event loop with asyncio
    while True:
        app.processEvents()
        await asyncio.sleep(0.01)

if __name__ == "__main__":
    asyncio.run(main())
