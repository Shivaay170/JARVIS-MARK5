import os
import io
import asyncio
import numpy as np

from jarvis.core.config import CONFIG, API_KEY
from jarvis.core.api import client

SAMPLE_RATE = 16000


class STT:
    """Speech-to-text.

    Default: Groq Whisper API (fast, free tier).
    Fallback: local faster-whisper when offline or the API fails.
    """

    def __init__(self):
        stt_cfg = CONFIG.get("settings", {}).get("stt", {})
        self.provider = stt_cfg.get("provider", "groq")
        self.model = stt_cfg.get("model", "whisper-large-v3-turbo")
        self.local_model = stt_cfg.get("local_model", "base.en")
        self.language = stt_cfg.get("language", "en")
        self._local = None
        self._local_failed = False

    # ---------- local fallback ----------

    def _get_local(self):
        if self._local is not None or self._local_failed:
            return self._local
        try:
            from faster_whisper import WhisperModel
            self._local = WhisperModel(self.local_model, device="cpu", compute_type="int8")
        except Exception as e:
            print(f"Local STT unavailable: {e}")
            self._local_failed = True
        return self._local

    def _transcribe_local(self, audio: np.ndarray) -> str:
        model = self._get_local()
        if model is None:
            return ""
        segments, _ = model.transcribe(audio, beam_size=1, language=self.language)
        return " ".join(seg.text for seg in segments).strip()

    # ---------- groq api ----------

    async def _transcribe_groq(self, audio: np.ndarray) -> str:
        import soundfile as sf

        buf = io.BytesIO()
        sf.write(buf, np.asarray(audio, dtype=np.float32), SAMPLE_RATE, format="WAV")
        buf.seek(0)
        buf.name = "audio.wav"

        resp = await client.audio.transcriptions.create(
            model=self.model,
            file=buf,
            response_format="json",
        )
        return (getattr(resp, "text", "") or "").strip()

    # ---------- public ----------

    async def transcribe(self, audio: np.ndarray) -> str:
        audio = np.asarray(audio, dtype=np.float32).flatten()
        if audio.size == 0:
            return ""
        if self.provider == "groq" and API_KEY:
            try:
                text = await self._transcribe_groq(audio)
                if text:
                    return text
            except Exception as e:
                print(f"Groq STT failed, using local fallback: {e}")
        return await asyncio.to_thread(self._transcribe_local, audio)


stt = STT()
