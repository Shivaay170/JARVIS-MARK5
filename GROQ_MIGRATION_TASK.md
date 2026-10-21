Phase 4. LLM calls use fast_model (gpt-oss-20b) unless noted. Minimize calls.

1. Speaker verification: sherpa-onnx speaker embeddings (ONNX, no torch). `python main.py enroll` records 10 phrases, saves mean embedding to data/voiceprint.npy. Verify every voice command (cosine threshold in config, stricter for CONFIRM-tier). On failure: ignore silently, log. Overlay text input is always trusted.

2. memory/store.py: SQLite WAL + FTS5; tables: facts, preferences, summaries, activity, profile. Extract durable facts once per session (after 2 min idle, one call for the whole session), not per turn. Before each agent call, inject profile summary (<=300 tokens) + top-5 FTS5 hits, placed after the static system prompt.

3. Pattern learning: log app usage by hour, commands used, accepted/rejected suggestions (batched writes). Rewrite profile summary at most once per day, one call.

4. Commands: "what do you know about me", "forget X", "forget everything".

5. data/profile.yaml: personal details for forms (I fill it myself); tool get_profile_field.