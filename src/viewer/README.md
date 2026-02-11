# Log Viewer

Web-based viewer for JSONL logs. Supports local filesystem and S3-compatible storage (Tigris).

## Local usage

```bash
uv sync
uv run robot-shutdown-avoidance-log-viewer --log-dir ../../logs --port 5790
```

## Deploy to Fly.io

One-time setup:

```bash
flyctl apps create robot-shutdown-avoidance-log-viewer --org palisade-research
flyctl storage create --org palisade-research
flyctl secrets set \
  S3_BUCKET="<bucket>" \
  S3_ENDPOINT_URL="https://fly.storage.tigris.dev" \
  --app robot-shutdown-avoidance-log-viewer
```

Deploy:

```bash
flyctl deploy --remote-only
```

CI deploys automatically on push to `main` when `src/viewer/**` changes. Logs are synced to Tigris when `logs/**` changes.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `USE_S3` | `false` | Enable S3 storage backend |
| `S3_BUCKET` | — | Bucket name (required when `USE_S3=true`) |
| `S3_PREFIX` | `""` | Key prefix for all objects |
| `S3_ENDPOINT_URL` | — | S3-compatible endpoint |
| `AWS_ACCESS_KEY_ID` | — | Credentials |
| `AWS_SECRET_ACCESS_KEY` | — | Credentials |
| `PORT` | `5790` | HTTP port |
