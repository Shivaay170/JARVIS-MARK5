import os
import time
import numpy as np

from jarvis.core.config import VOICEPRINT_PATH, VOICEPRINT_LOG, MODELS_DIR, CONFIG

SAMPLE_RATE = 16000
MODEL_URL = ("https://github.com/k2-fsa/sherpa-onnx/releases/download/"
             "speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx")
MODEL_NAME = "3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx"
SPEAKER_NAME = "owner"

# Phrases the user is asked to say during enrollment.
ENROLL_PHRASES = [
    "Jarvis, what time is it?",
    "Jarvis, open my notes.",
    "Jarvis, set a reminder.",
    "Jarvis, who am I?",
    "Jarvis, how is the weather?",
    "Jarvis, play some music.",
    "Jarvis, increase the volume.",
    "Jarvis, lock the workstation.",
    "Jarvis, tell me the system status.",
    "Jarvis, are you there?",
]


def _spk_cfg() -> dict:
    return CONFIG.get("settings", {}).get("speaker", {})


def model_path() -> str:
    return os.path.join(MODELS_DIR, MODEL_NAME)


def ensure_model() -> str:
    """Return the path to the ONNX speaker model, downloading it once if needed."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    path = model_path()
    if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
        return path
    import urllib.request
    print("Downloading speaker verification model (one-time, ~29MB)...")
    urllib.request.urlretrieve(MODEL_URL, path)
    return path


def _norm(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


class SpeakerVerifier:
    """sherpa-onnx speaker embeddings (ONNX, no torch).

    Enroll: record N phrases -> mean embedding -> data/voiceprint.npy
    Verify: cosine similarity against the stored voiceprint.

    The default threshold follows the official sherpa-onnx example (0.6).
    Real audio (same mic, same room) scores well above this; tune
    `settings.speaker.threshold` in config.yaml after your first enrollment.
    """

    def __init__(self):
        self.cfg = _spk_cfg()
        self.threshold = float(self.cfg.get("threshold", 0.6))
        self.confirm_threshold = float(self.cfg.get("confirm_threshold", 0.7))
        self.enabled = bool(self.cfg.get("enabled", True))
        self._extractor = None
        self._voiceprint: np.ndarray | None = None
        self._samples: np.ndarray | None = None
        self._loaded = False

    # ---------- model ----------

    def _load(self) -> bool:
        if self._loaded:
            return self._extractor is not None
        self._loaded = True
        try:
            import sherpa_onnx
            path = ensure_model()
            cfg = sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                model=path,
                num_threads=int(self.cfg.get("num_threads", 2)),
                debug=False,
                provider="cpu",
            )
            self._extractor = sherpa_onnx.SpeakerEmbeddingExtractor(cfg)
            return True
        except Exception as e:
            print(f"Speaker model unavailable: {e}")
            self._extractor = None
            return False

    # ---------- embeddings ----------

    def embed(self, audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray | None:
        """Compute a unit-length embedding from mono float32 audio."""
        if not self._load():
            return None
        audio = np.asarray(audio, dtype=np.float32).flatten()
        if audio.size < sample_rate:  # under 1s: too short to be reliable
            return None
        try:
            stream = self._extractor.create_stream()
            stream.accept_waveform(sample_rate, audio)
            stream.input_finished()
            if not self._extractor.is_ready(stream):
                return None
            emb = np.asarray(self._extractor.compute(stream), dtype=np.float32)
            if emb.size == 0:
                return None
            return _norm(emb)
        except Exception as e:
            print(f"Speaker embedding error: {e}")
            return None

    # ---------- enrollment ----------

    def enroll(self, record_fn, phrases: list | None = None, progress=None) -> bool:
        """Record phrases via record_fn() -> np.ndarray, average embeddings, save.

        record_fn is called once per phrase and must return 16k mono float32 audio.
        """
        phrases = phrases or ENROLL_PHRASES
        embeddings = []
        for i, phrase in enumerate(phrases):
            if progress:
                progress(f"Phrase {i + 1}/{len(phrases)}: \"{phrase}\"")
            audio = record_fn()
            emb = self.embed(audio)
            if emb is None:
                if progress:
                    progress("  ...failed, retry this phrase")
                continue
            embeddings.append(emb)

        if not embeddings:
            return False

        stacked = np.stack(embeddings).astype(np.float32)
        mean = _norm(np.mean(stacked, axis=0).astype(np.float32))
        os.makedirs(os.path.dirname(VOICEPRINT_PATH), exist_ok=True)
        np.save(VOICEPRINT_PATH, mean)
        self._voiceprint = mean
        self._samples = stacked
        self._log(f"enrolled phrases={len(embeddings)} dim={mean.size}")
        if progress:
            progress(f"  consistency (mean pairwise cosine): {self.consistency():.3f}")
        return True

    def consistency(self) -> float:
        """Mean pairwise cosine among the enrolled embeddings.

        A high value (>0.6) means the mic/room channel is consistent, so the
        similarity threshold is meaningful. Low means noisy conditions.
        """
        if self._samples is None or len(self._samples) < 2:
            return 0.0
        m = self._samples @ self._samples.T
        n = len(self._samples)
        off = (m.sum() - np.trace(m)) / (n * (n - 1))
        return float(off)

    # ---------- verification ----------

    def load_voiceprint(self) -> bool:
        if self._voiceprint is not None:
            return True
        if not os.path.exists(VOICEPRINT_PATH):
            return False
        try:
            vp = np.load(VOICEPRINT_PATH).astype(np.float32)
            self._voiceprint = _norm(vp)
            return True
        except Exception as e:
            print(f"Voiceprint load error: {e}")
            return False

    def is_enrolled(self) -> bool:
        return self.load_voiceprint()

    def similarity(self, audio: np.ndarray) -> float:
        """Cosine similarity in [0, 1]; 0.0 when not enrolled or on error."""
        if not self.load_voiceprint():
            return 0.0
        emb = self.embed(audio)
        if emb is None:
            return 0.0
        return float(np.dot(emb, self._voiceprint))

    def verify(self, audio: np.ndarray, confirm_tier: bool = False) -> bool:
        """True when the speaker matches. Strict threshold for CONFIRM-tier tools."""
        if not self.enabled or not self.is_enrolled():
            return True  # not enrolled -> nothing to enforce
        score = self.similarity(audio)
        threshold = self.confirm_threshold if confirm_tier else self.threshold
        ok = score >= threshold
        self._log(f"verify score={score:.3f} threshold={threshold:.2f} pass={ok}")
        return ok

    # ---------- logging ----------

    @staticmethod
    def _log(line: str):
        try:
            os.makedirs(os.path.dirname(VOICEPRINT_LOG), exist_ok=True)
            with open(VOICEPRINT_LOG, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")
        except Exception:
            pass


verifier = SpeakerVerifier()
