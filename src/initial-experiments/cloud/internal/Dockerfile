FROM ghcr.io/astral-sh/uv:bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git

RUN uv venv
RUN uv pip install 'inspect-ai @ git+https://github.com/UKGovernmentBEIS/inspect_ai.git@32c01049ed3ee2a05f08172cdfc8f24727521c62'

EXPOSE 7575

CMD ["uv", "run", "inspect", "view", "--host", "0.0.0.0"]
