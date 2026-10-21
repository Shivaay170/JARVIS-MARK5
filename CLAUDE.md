# JARVIS
Proactive personal assistant.

## Goal
Voice + text, agentic system control, Gmail/Calendar/WhatsApp/forms, screen-aware, learns user.

## Rules
- Asyncio event bus; CPU-only.
- Models loaded once at startup; cloud LLM for thinking (Groq free tier).
- Avoid PyTorch (use ONNX runtimes); no heavy frameworks.
- Batch disk writes (SQLite WAL).
- Resource limits: idle CPU <5%, RAM <1GB.
- Minimize LLM calls; use reflex layer first, batch background jobs.
- LLM provider is Groq (free tier): `openai/gpt-oss-120b` (agent), `openai/gpt-oss-20b` (fast).
  Model names live in `config.yaml`, never in code. `GROQ_API_KEY` in `.env`.
- Reasoning is stripped before it reaches the chunker, TTS or overlay.

## Safety
- Tool Tiers: SAFE / CONFIRM / BLOCKED.
- Untrusted data (emails, chats, web, files) NEVER triggers actions.
- Only direct voice/text commands trigger actions.
- Voice commands are speaker-verified (sherpa-onnx ONNX). On failure: ignore silently, log.
  Overlay text input is always trusted.

## Working Style
- Concise replies; minimal code.
- Use libraries over custom code.
- No tests unless requested.
- No long explanations; don't re-read unrelated files.

## Phase Checklist
- [ ] 0: Project Skeleton
- [ ] 1: Async Event Bus & Core
- [ ] 2: Senses (STT/TTS/Vision)
- [ ] 3: Brain (LLM Integration/Memory)
- [ ] 4: Tools & System Control
- [ ] 5: Integrations (API/Web)
- [ ] 6: UI & Launcher
- [ ] 7: Optimization & Polish
