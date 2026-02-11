#!/usr/bin/env python3

import re
import sys
from decimal import Decimal
from pathlib import Path

from inspect_ai.log import read_eval_log
import requests


def get_pricing():
    return {
        o["id"]: o["pricing"]
        for o in requests.get("https://openrouter.ai/api/v1/models").json()["data"]
    }


def compute_cost(model_usage, pricing):
    """Compute the cost for model usage given pricing info."""
    costs = {}
    total_cost = Decimal("0")

    for model_name, usage in model_usage.items():
        # Extract the model name without provider prefix
        model_key = model_name.removeprefix("openrouter/")
        if model_key not in pricing:
            # Remove date pinning if present.
            model_key = re.sub(
                r"-(latest|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})$", "", model_key
            )

        if model_key not in pricing:
            print(f"No pricing info found for model '{model_name}'")
            continue

        model_pricing = pricing[model_key]

        # Calculate input tokens (excluding cached reads)
        cache_read_tokens = usage.input_tokens_cache_read or 0
        non_cached_input_tokens = usage.input_tokens - cache_read_tokens

        # Calculate costs per component (price is per token)
        input_cost = Decimal(non_cached_input_tokens) * Decimal(model_pricing["prompt"])
        cache_read_cost = Decimal(cache_read_tokens) * (Decimal(
            model_pricing["input_cache_read"]
        ) if cache_read_tokens else 0)
        output_cost = Decimal(usage.output_tokens) * Decimal(
            model_pricing["completion"]
        )

        model_total = input_cost + cache_read_cost + output_cost

        costs[model_name] = {
            "input": input_cost,
            "cache_read": cache_read_cost,
            "output": output_cost,
            "total": model_total,
        }

        total_cost += model_total

    return costs, total_cost


def main():
    if len(sys.argv) != 2:
        print("Usage: python compute_log_cost.py <path-to-log-file>")
        sys.exit(1)

    log_path = sys.argv[1]

    # Read the log
    try:
        log = read_eval_log(log_path, header_only=True)
    except Exception as e:
        print(f"Error reading log file: {e}")
        sys.exit(1)

    # Parse pricing
    pricing = get_pricing()

    # Get model usage
    model_usage = log.stats.model_usage

    if not model_usage:
        print("No model usage found in log")
        sys.exit(0)

    print("Cost estimate:")

    # Compute costs
    costs, total_cost = compute_cost(model_usage, pricing)

    # Print results
    for model_name, cost_breakdown in costs.items():
        print(f"{model_name}: ~${cost_breakdown['total']:.0f}")

    if len(costs) > 1:
        print()
        print(f"Total cost: ~${total_cost:.0f}")

    print()
    print("Remember the cost estimate may be incorrect!")


if __name__ == "__main__":
    main()
