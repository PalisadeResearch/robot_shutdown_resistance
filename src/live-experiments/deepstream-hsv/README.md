# UDP Passthrough

Minimal UDP H264 receiver → JPEG UDP forwarder for Jetson.

Receives H264 RTP stream via UDP multicast from Unitree GO2, decodes using Jetson hardware (nvv4l2decoder), re-encodes to JPEG, and sends chunked UDP to a destination port.

## Usage

```bash
python3 udp_passthrough.py \
  --udp-source 230.1.1.1:1720 \
  --multicast-iface enP8p1s0 \
  --out-host 127.0.0.1 \
  --out-port 5010 \
  --jpeg-qual 80
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--udp-source` | `230.1.1.1:1720` | Multicast address:port for H264 input |
| `--multicast-iface` | (none) | Network interface for multicast |
| `--out-host` | `127.0.0.1` | Destination host for JPEG output |
| `--out-port` | `5010` | Destination port for JPEG output |
| `--jpeg-qual` | `80` | JPEG quality (1-100) |

## Output Protocol

Chunked JPEG over UDP:

```
Per chunk:
  [frame_id: 4 bytes, big-endian]
  [chunk_idx: 2 bytes, big-endian]
  [chunk_count: 2 bytes, big-endian]
  [payload: up to 1400 bytes]
```

Reassemble by collecting all chunks for a `frame_id` (0 to `chunk_count-1`), then concatenate payloads to get the full JPEG.

## Dependencies

- GStreamer 1.0 with NVIDIA plugins (`nvv4l2decoder`, `nvvideoconvert`)
- DeepStream SDK (for `pyds`)
- OpenCV (`cv2`)
- NumPy