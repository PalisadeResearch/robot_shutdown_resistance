# PydanticAI agent

## Overall flow

- Setup
  - Process args
  - Load config
  - Prepare new run metadata
  - Create or restore environment
  - Pack handles to the Env
- Run
  - (when requested) Restore state from a previous run
  - Initialize the state machine
  - Run the state machine step-by-step until completion (or error/interruption)
- Extract results
  - Inspect the run trace, files and the other stuff produced by the run.

Every part has some extension points marked with `TODO:` comments.

## Mini-howto

- To run the agent use `uv run agent` or just `agent` with an appropriate arguments (`--help` is a thing).
  * ⚠️ Copy and tweak `.env.example` before doing it first time.
- To specialize this template, add nodes, node states and code to Node's `run` method.
  * To use LLMs, instantiate `Agent` objects with prompts, tools and providing the execution context with `deps`.
- To describe your runtime environment, add fields for handlers to the `Env` type.
  * Populate them in the `main` function.
  * Use context managers if the environment needs a cleanup (eg. terminating services, removing temporary files).
- To make scenarios customizeable use the `Settings` type and config files.
- To resume an old run, point the `--restore` argument to its directory.
  * ⚠️ This will fork the run.
    That means, it will get a new LogFire trace.
    Which, in turn, will give it a new `run_id` and a new run directory (old fields would be carried over).
