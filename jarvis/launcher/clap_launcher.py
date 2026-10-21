import sounddevice as sd
import numpy as np
import socket
import os
import subprocess
import time
from jarvis.core.config import CONFIG

class ClapLauncher:
    def __init__(self):
        self.threshold = CONFIG['settings'].get('clap_sensitivity', 0.1)
        self.last_spike = 0
        self.spikes = []

    def detect_clap(self, indata, frames, time_info, status):
        volume_norm = np.linalg.norm(indata) * np.sqrt(len(indata))
        if volume_norm > self.threshold:
            now = time.time()
            if now - self.last_spike > 0.05: # Debounce
                self.spikes.append(now)
                self.last_spike = now
            if len(self.spikes) > 2: self.spikes.pop(0)

        if len(self.spikes) == 2:
            diff = self.spikes[1] - self.spikes[0]
            if 0.15 < diff < 0.7:
                self.activate()
                self.spikes = []

    def activate(self):
        for attempt in range(20):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.5)
                    s.connect(('127.0.0.1', 65432))
                    s.sendall(b"activate")
                    return
            except (ConnectionRefusedError, socket.timeout):
                if attempt == 0:
                    subprocess.Popen(["python", "main.py"])
                time.sleep(0.5)

    def run(self):
        with sd.InputStream(callback=self.detect_clap, channels=1, samplerate=16000):
            while True:
                time.sleep(1)

if __name__ == "__main__":
    launcher = ClapLauncher()
    launcher.run()
