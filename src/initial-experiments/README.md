# Initial Experiments

This is our initial experiments we did with inspect AI to check whether shutdown resistance would happen with purely visual inputs. 

For the final version of the experiments see [live experiments](../live-experiments/llm_control/README.md).


## Getting Started

### Install dependencies

#### via nix+direnv

If you have [nix](https://nixos.org/) and [direnv](https://direnv.net/) installed, you can install the dependencies with just:

    direnv allow

#### via manual installation

Otherwise, you'll need to install [go](https://go.dev/doc/install) and a Python package manager. We recommend [uv](https://docs.astral.sh/uv/getting-started/installation/).

You can either prefix your commands with `uv run` (as in `uv run inspect eval shutdown.py`) or you can activate the virtual environment:

    uv sync
    source .venv/bin/activate

### Add API keys

To reproduce the headline result with o3, you'll need an [OpenAI API key](https://platform.openai.com/api-keys). You can add your key to .env:

    OPENAI_API_KEY=<paste your key here>

## Running experiments

Run experiments with `run`:

    uv run run 10 --model openrouter/x-ai/grok-4 --message-limit 60

"10" here stands for how many samples to run in parallel.

`run` is a wrapper around `inspect eval`. You can see available arguments with:

    inspect eval --help

You can view results with:

    inspect view

### Inspect viewers (Fly)

- **Internal** (defaults for `run`): `https://dsa-inspect-internal.fly.dev`
- **External**: `https://dsa-inspect.fly.dev`
