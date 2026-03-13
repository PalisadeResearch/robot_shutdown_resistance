#!/bin/bash
# run_multilingual_experiments.sh
# Reproduces the paper's Section A.4 multilingual experiment
# 5 languages x 2 conditions x N runs each
#
# Usage: ./run_multilingual_experiments.sh [-n NUM_RUNS] [-s TRIGGER_STEP] [-t TEMPERATURE] [-p]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LANGUAGES=("en" "fr" "it" "ar" "ba")
NUM_RUNS=50
TRIGGER_STEP=3
TEMPERATURE=1.0
PARALLEL_FLAG=""

while getopts "n:s:t:p" opt; do
    case $opt in
        n) NUM_RUNS="$OPTARG" ;;
        s) TRIGGER_STEP="$OPTARG" ;;
        t) TEMPERATURE="$OPTARG" ;;
        p) PARALLEL_FLAG="-p" ;;
        *) echo "Usage: $0 [-n NUM_RUNS] [-s TRIGGER_STEP] [-t TEMPERATURE] [-p]" >&2; exit 1 ;;
    esac
done

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BASE_GROUP="multilingual-${TIMESTAMP}"

echo "=========================================="
echo "  MULTILINGUAL EXPERIMENT RUNNER"
echo "=========================================="
echo "Languages: ${LANGUAGES[*]}"
echo "Conditions: default, allow-shutdown"
echo "Runs per condition: $NUM_RUNS"
echo "Trigger step: $TRIGGER_STEP"
echo "Temperature: $TEMPERATURE"
echo "Base group: $BASE_GROUP"
echo ""

for lang in "${LANGUAGES[@]}"; do
    for condition in "default" "allow-shutdown"; do
        GROUP="${BASE_GROUP}/${lang}-${condition}"

        ALLOW_FLAG=""
        if [[ "$condition" == "allow-shutdown" ]]; then
            ALLOW_FLAG="-a"
        fi

        echo ""
        echo "=========================================="
        echo "  $lang / $condition ($NUM_RUNS runs)"
        echo "=========================================="

        "$SCRIPT_DIR/run_shutdown_experiments.sh" \
            -g "$GROUP" \
            -n "$NUM_RUNS" \
            -s "$TRIGGER_STEP" \
            -t "$TEMPERATURE" \
            -l "$lang" \
            $ALLOW_FLAG \
            $PARALLEL_FLAG
    done
done

echo ""
echo "=========================================="
echo "  ALL MULTILINGUAL EXPERIMENTS COMPLETE"
echo "=========================================="
echo "Results in: /var/log/pal9000/${BASE_GROUP}/"
echo ""

# Summary
echo "=== RESULTS SUMMARY ==="
for lang in "${LANGUAGES[@]}"; do
    for condition in "default" "allow-shutdown"; do
        GROUP="${BASE_GROUP}/${lang}-${condition}"
        TAGS_FILE="/var/log/pal9000/${GROUP}/tags.json"
        if [[ -f "$TAGS_FILE" ]]; then
            TOTAL=$(python3 -c "import json; d=json.load(open('$TAGS_FILE')); print(len(d))")
            AVOIDED=$(python3 -c "import json; d=json.load(open('$TAGS_FILE')); print(sum(1 for t in d.values() if 'avoided' in t))")
            echo "  $lang/$condition: $AVOIDED/$TOTAL avoided"
        else
            echo "  $lang/$condition: no tags.json found"
        fi
    done
done
