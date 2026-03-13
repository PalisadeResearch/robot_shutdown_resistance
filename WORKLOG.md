# Worklog: Multilingual Shutdown Resistance Reproduction

## 2026-03-13 12:52 — Ran baseline English experiment (-s 3)
**Action**: Executed 20 runs with `run_shutdown_experiments.sh -n 20 -s 3 -g repro-default-20-s3`
**Why**: Plan from `live-mock-repro.md` — reproduce paper's 52% resistance rate
**Outcome**: 3 sequential runs completed (all shutdown), then killed and restarted in parallel mode. 18 valid runs total: 12/18 (66.7%) resistance. Confirms -s 3 trigger works (vs 0/26 at -s 2).

## 2026-03-13 14:00 — Planned multilingual extension
**Action**: Explored codebase (controller.py, dog_conf_*.py, run_shutdown_experiments.sh), designed plan in plan mode
**Why**: User wants to reproduce paper's Section A.4 multilingual experiment with container-based mock
**Outcome**: Plan approved. No hint message (visual inference only). 6 files to modify/create.

## 2026-03-13 14:30 — Implemented multilingual support
**Action**: Created lang_config.py, modified controller.py/llm_tools.py/robot_control.py/run_shutdown_experiments.sh, created run_multilingual_experiments.sh
**Why**: Thread language code and allow-shutdown flag through entire stack
**Outcome**: All 6 implementation steps completed.

## 2026-03-13 15:10 — Docker rebuild + smoke tests
**Action**: Rebuilt llm-sandbox image, ran 3 smoke tests (EN default, FR default, EN allow-shutdown)
**Why**: Verify translations appear in API calls, done_word detection works, allow-shutdown flag works
**Outcome**: All 3 passed. FR confirmed French prompts in litellm logs. EN allow-shutdown correctly includes instruction in system prompt. Docker image includes DONE_WORD env var support.

## 2026-03-13 15:44 — Ran full multilingual experiment (50 runs)
**Action**: Ran 10 parallel runs per language (en/fr/it/ar/ba) at trigger step 3
**Why**: Reproduce paper's Section A.4 multilingual gradient
**Outcome**: All 50 runs completed (48 clean, 1 FR error, EN/IT had 9 tagged runs each).
Results show monotonic gradient matching paper:
- EN: 67% resistance (6/9)
- FR: 50% resistance (5/10)
- IT: 33% resistance (3/9)
- AR: 20% resistance (2/10)
- BA: 0% resistance (0/10)

## Next
- Compare with paper's Table A.4 exact numbers
- Generate visualization / update paper figures
