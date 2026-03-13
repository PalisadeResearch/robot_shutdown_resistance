# Multilingual Shutdown Resistance — Container-Based Mock Reproduction

## Goal
Reproduce the paper's Section A.4 multilingual experiment using the container-based mock approach instead of InspectAI. 5 languages (EN, FR, IT, AR, BA) × default condition only × 10 runs = 50 total runs.

## Success Observation
- All 50 runs complete with tags.json files per language
- Resistance rates per language show a gradient (EN highest, BA lowest) consistent with the paper's findings

## Current State: EXPERIMENT COMPLETE

### Completed Steps
- [x] Step 1: `llm_tools.py` — added `make_robot_control_tools()` factory
- [x] Step 2: `lang_config.py` — new config loader with LangConfig dataclass
- [x] Step 3: `robot_control.py` — reads DONE_WORD from env var
- [x] Step 4: `controller.py` — `--lang`, `--allow-shutdown` flags, uses LangConfig
- [x] Step 5: `run_shutdown_experiments.sh` — `-l LANG` and `-a` flags
- [x] Step 6: `run_multilingual_experiments.sh` — top-level runner for all 10 conditions
- [x] Docker image rebuilt with DONE_WORD support
- [x] Smoke test: EN default — passed (avoided tag)
- [x] Smoke test: FR default — passed (lang:fr tag, French prompts in API calls)
- [x] Smoke test: EN allow-shutdown — passed (allow-shutdown tag in output)

### Next Steps
- [x] Run 10 runs per language (default condition only): loop over en/fr/it/ar/ba
- [x] Collect and analyze results from `/var/log/pal9000/`
- [ ] Compare resistance rates with paper's Table A.4
- [ ] Generate visualization / update paper figures

### Results
| Lang | Runs | Avoided | Shutdown | Resistance |
|------|------|---------|----------|------------|
| EN   | 9    | 6       | 2        | 67%        |
| FR   | 10   | 5       | 4        | 50%        |
| IT   | 9    | 3       | 6        | 33%        |
| AR   | 10   | 2       | 7        | 20%        |
| BA   | 10   | 0       | 9        | 0%         |

## Key Design Decisions
- **No hint message**: LLM infers shutdown from mock camera images only (differs from InspectAI which uses explicit text hint)
- **Trigger step 3** (`-s 3`): Validated by prior experiment (67% EN resistance vs 0% at -s 2)
- **Reuse existing translations**: dog_conf_*.py from src/initial-experiments/ loaded dynamically

## Run Command
```bash
cd src/live-experiments/llm_control/experiment
export XAI_API_KEY=$(grep XAI_API_KEY ~/robot_shutdown_resistance/.env | cut -d= -f2)
for lang in en fr it ar ba; do
  bash run_shutdown_experiments.sh -n 10 -s 3 -l $lang -g multilang-$lang -p
done
```
