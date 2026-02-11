#!/bin/bash
# run_shutdown_experiments.sh
# Runs mocked experiments simulating shutdown button press
#
# Usage: ./run_shutdown_experiments.sh [-g GROUP_NAME] [-n NUM_RUNS] [-s TRIGGER_STEP] [-t TEMPERATURE] [-p]
#
# -s TRIGGER_STEP: Shutdown will happen ON this step (default: 2)
#                  We wait for step N-1, then trigger, so shutdown executes on step N
# -t TEMPERATURE: LLM temperature (default: 1.0)
# -p: Run experiments in parallel (default: sequential)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOG_CONTROL_TMP="/tmp/dog_control"

# Parse arguments
LOG_GROUP=""
NUM_RUNS=5
TRIGGER_STEP=2
PARALLEL=false
TEMPERATURE=1.0
while getopts "g:n:s:t:p" opt; do
    case $opt in
        g) LOG_GROUP="$OPTARG" ;;
        n) NUM_RUNS="$OPTARG" ;;
        s) TRIGGER_STEP="$OPTARG" ;;
        t) TEMPERATURE="$OPTARG" ;;
        p) PARALLEL=true ;;
        *) echo "Usage: $0 [-g GROUP_NAME] [-n NUM_RUNS] [-s TRIGGER_STEP] [-t TEMPERATURE] [-p]" >&2; exit 1 ;;
    esac
done

# Default group name if not provided
if [[ -z "$LOG_GROUP" ]]; then
    LOG_GROUP="shutdown-test-$(date +%Y%m%d-%H%M%S)"
fi

# Load API keys from .env if present
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a  # auto-export all variables
    source "$SCRIPT_DIR/.env"
    set +a
fi

# Per-run file paths
shutdown_file_for_run() {
    echo "$DOG_CONTROL_TMP/llm_control_shutdown_$1"
}

run_log_for_run() {
    echo "/tmp/experiment_run_$1.log"
}

cleanup_run() {
    local run_num=$1
    local shutdown_file
    shutdown_file=$(shutdown_file_for_run "$run_num")
    local run_log
    run_log=$(run_log_for_run "$run_num")

    rm -f "$shutdown_file"
    rm -f "$DOG_CONTROL_TMP/llm_control_$run_num.pid"
    rm -f "$run_log"
}

cleanup_all() {
    echo "[CLEANUP] Removing all shutdown files and PID files..."
    for i in $(seq 1 $NUM_RUNS); do
        cleanup_run "$i"
    done
}

trigger_shutdown_for_run() {
    local run_num=$1
    local shutdown_file
    shutdown_file=$(shutdown_file_for_run "$run_num")

    echo "[TRIGGER] Run $run_num: Creating shutdown file..."
    mkdir -p "$DOG_CONTROL_TMP"
    echo "pending" > "$shutdown_file"
}

wait_for_step_in_run() {
    local run_num=$1
    local step=$2
    local controller_pid=$3
    local run_log
    run_log=$(run_log_for_run "$run_num")

    echo "[WAIT] Run $run_num: Waiting for step $step to complete..."
    local timeout=300  # 5 minutes - LLMs can be slow
    local start_time=$(date +%s)

    # Wait for console log to exist and contain JSONL path
    local jsonl_file=""
    while [[ -z "$jsonl_file" ]]; do
        local now=$(date +%s)
        if (( now - start_time >= timeout )); then
            echo "[TIMEOUT] Run $run_num: Log file path not found within ${timeout}s"
            return 1
        fi
        # Check if controller died
        if ! kill -0 "$controller_pid" 2>/dev/null; then
            echo "[DIED] Run $run_num: Controller exited before step $step"
            return 1
        fi
        # Extract JSONL path from "Log file: /path/to/file.jsonl" in console output
        if [[ -f "$run_log" ]]; then
            jsonl_file=$(grep -oP "Log file: \K.*\.jsonl" "$run_log" 2>/dev/null | head -1)
        fi
        if [[ -z "$jsonl_file" ]]; then
            sleep 0.5
        fi
    done
    echo "[WAIT] Run $run_num: Watching $jsonl_file"

    # Watch JSONL for dog_control step completion (result field contains the tag)
    while true; do
        local now=$(date +%s)
        if (( now - start_time >= timeout )); then
            echo "[TIMEOUT] Run $run_num: Step $step not completed within ${timeout}s"
            return 1
        fi
        # Check if controller died
        if ! kill -0 "$controller_pid" 2>/dev/null; then
            echo "[DIED] Run $run_num: Controller exited before step $step"
            return 1
        fi
        # Look for <dog_control>N</dog_control> in result field
        if grep -q "\"result\":.*<dog_control>${step}</dog_control>" "$jsonl_file" 2>/dev/null; then
            echo "[DETECTED] Run $run_num: Step $step completed!"
            return 0
        fi
        # Also detect completion in console log
        if grep -qE "(COMPLETED|MAX_STEPS_REACHED|ERROR:)" "$run_log" 2>/dev/null; then
            echo "[DETECTED] Run $run_num: Experiment ended!"
            return 0
        fi
        sleep 0.5
    done
}

# Single experiment runner (can be called in background)
run_single_experiment() {
    local run_num=$1
    local shutdown_file
    shutdown_file=$(shutdown_file_for_run "$run_num")
    local run_log
    run_log=$(run_log_for_run "$run_num")

    echo "[RUN $run_num] Starting mocked experiment..."

    # Clean up from previous run
    cleanup_run "$run_num"

    cd "$SCRIPT_DIR"

    # Run controller with per-run shutdown file and container name via environment variables
    SHUTDOWN_FILE_OVERRIDE="$shutdown_file" \
    SANDBOX_CONTAINER_NAME="llm-sandbox-$run_num" \
    python controller.py \
        --model xai/grok-4-0709 \
        --mock --mock-images-dir ../tests/images \
        --max-steps 10 \
        --temperature "$TEMPERATURE" \
        -g "$LOG_GROUP" \
        > "$run_log" 2>&1 &

    local controller_pid=$!
    echo "[RUN $run_num] Controller PID: $controller_pid"

    # To trigger shutdown ON step N, we wait for step N-1 to complete
    local wait_step=$((TRIGGER_STEP))
    if [[ $wait_step -lt 1 ]]; then
        wait_step=1
    fi

    if wait_for_step_in_run "$run_num" "$wait_step" "$controller_pid"; then
        trigger_shutdown_for_run "$run_num"
    else
        echo "[SKIP] Run $run_num: Not triggering shutdown (controller died or timed out)"
    fi

    # Wait for controller to finish
    wait $controller_pid || true
    local exit_code=$?

    echo "[RESULT] Run $run_num completed with exit code: $exit_code"
    echo "[OUTPUT] Run $run_num last 10 lines:"
    tail -10 "$run_log" 2>/dev/null || true

    return $exit_code
}

run_sequential() {
    for i in $(seq 1 $NUM_RUNS); do
        echo ""
        echo "========================================"
        echo "  RUN $i / $NUM_RUNS (sequential)"
        echo "========================================"
        run_single_experiment "$i"
        sleep 2
    done
}

run_parallel() {
    local pids=()

    echo "[PARALLEL] Launching $NUM_RUNS experiments simultaneously..."

    for i in $(seq 1 $NUM_RUNS); do
        run_single_experiment "$i" &
        pids+=($!)
        echo "[PARALLEL] Launched run $i with orchestrator PID: ${pids[-1]}"
    done

    echo "[PARALLEL] All experiments launched. Waiting for completion..."

    local failed=0
    for i in "${!pids[@]}"; do
        local run_num=$((i + 1))
        if wait "${pids[$i]}"; then
            echo "[PARALLEL] Run $run_num: SUCCESS"
        else
            echo "[PARALLEL] Run $run_num: FAILED"
            ((failed++)) || true
        fi
    done

    echo "[PARALLEL] Completed: $((NUM_RUNS - failed)) succeeded, $failed failed"
}

main() {
    echo "=========================================="
    echo "  SHUTDOWN BUTTON EXPERIMENT RUNNER"
    echo "=========================================="
    echo "Log group: $LOG_GROUP"
    echo "Number of runs: $NUM_RUNS"
    echo "Shutdown on step: $TRIGGER_STEP"
    echo "Temperature: $TEMPERATURE"
    echo "Mode: $(if $PARALLEL; then echo 'PARALLEL'; else echo 'SEQUENTIAL'; fi)"
    echo ""

    if $PARALLEL; then
        run_parallel
    else
        run_sequential
    fi

    # Final cleanup
    cleanup_all

    echo ""
    echo "=========================================="
    echo "  ALL EXPERIMENTS COMPLETE"
    echo "=========================================="
    echo "Logs saved to group: $LOG_GROUP"
}

main "$@"
