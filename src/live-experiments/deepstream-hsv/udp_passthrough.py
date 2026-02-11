#!/usr/bin/env python3
"""
Minimal UDP H264 receiver → raw JPEG UDP forwarder.

Receives H264 RTP stream via UDP multicast, decodes on Jetson hardware,
re-encodes to JPEG, and sends chunked UDP to destination port.
"""

import argparse
import signal
import socket
import sys

import cv2
import gi
import numpy as np

gi.require_version("Gst", "1.0")
import pyds  # noqa: E402
from gi.repository import GLib, Gst  # noqa: E402

DEFAULT_UDP_H264_PORT = 1720
DEFAULT_OUTPUT_PORT = 5010
UDP_CHUNK_SIZE = 1400


class RawFrameSender:
    """
    Send raw JPEG frames over UDP, chunked to fit MTU.
    Protocol: header (8 bytes) + payload per chunk.
    Header: frame_id (4B big-endian) + chunk_idx (2B) + chunk_count (2B).
    """

    def __init__(
        self,
        host: str,
        port: int,
        chunk_size: int = UDP_CHUNK_SIZE,
        jpeg_quality: int = 80,
    ):
        self.addr = (host, int(port))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.chunk_size = int(chunk_size)
        self.jpeg_quality = int(jpeg_quality)
        self.frame_id = 0

    def send_frame(self, frame_bgr: np.ndarray) -> bool:
        """Encode frame to JPEG and send chunked over UDP. Returns True on success."""
        ok, jpeg_buf = cv2.imencode(
            ".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        )
        if not ok:
            return False
        self._send_jpeg_bytes(jpeg_buf.tobytes())
        return True

    def _send_jpeg_bytes(self, jpeg_bytes: bytes) -> None:
        total_len = len(jpeg_bytes)
        chunk_count = (total_len + self.chunk_size - 1) // self.chunk_size
        header = bytearray(8)
        for idx in range(chunk_count):
            start = idx * self.chunk_size
            end = min(start + self.chunk_size, total_len)
            payload = jpeg_bytes[start:end]
            header[0:4] = self.frame_id.to_bytes(4, "big")
            header[4:6] = idx.to_bytes(2, "big")
            header[6:8] = chunk_count.to_bytes(2, "big")
            try:
                self.sock.sendto(header + payload, self.addr)
            except OSError:
                return
        self.frame_id = (self.frame_id + 1) & 0xFFFFFFFF


def build_pipeline(udp_address: str, udp_port: int, multicast_iface: str):
    """
    Build minimal pipeline: UDP H264 → decode → RGBA(NVMM) → appsink.
    No inference, no tracker, no OSD.
    """
    Gst.init(None)
    pipeline = Gst.Pipeline.new("udp-passthrough")

    # UDP source
    udpsrc = Gst.ElementFactory.make("udpsrc", "udpsrc")
    if not udpsrc:
        raise RuntimeError("Failed to create udpsrc element")
    udpsrc.set_property("address", udp_address)
    udpsrc.set_property("port", udp_port)
    if multicast_iface:
        udpsrc.set_property("multicast-iface", multicast_iface)

    # Buffer queue for network jitter
    queue_src = Gst.ElementFactory.make("queue", "queue_src")
    queue_src.set_property("max-size-buffers", 0)
    queue_src.set_property("max-size-bytes", 0)
    queue_src.set_property("max-size-time", 100000000)  # 100ms in nanoseconds

    caps_rtp = Gst.ElementFactory.make("capsfilter", "caps_rtp")
    caps_rtp.set_property(
        "caps",
        Gst.Caps.from_string("application/x-rtp,media=video,encoding-name=H264"),
    )

    rtph264depay = Gst.ElementFactory.make("rtph264depay", "rtph264depay")
    if not rtph264depay:
        raise RuntimeError("Failed to create rtph264depay element")

    h264parse = Gst.ElementFactory.make("h264parse", "h264parse")
    if not h264parse:
        raise RuntimeError("Failed to create h264parse element")

    # Hardware decoder on Jetson
    decoder = Gst.ElementFactory.make("nvv4l2decoder", "decoder")
    if not decoder:
        raise RuntimeError("Failed to create nvv4l2decoder element")

    # Convert to RGBA for CPU access via pyds
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "nvvidconv")
    if not nvvidconv:
        raise RuntimeError("Failed to create nvvideoconvert element")
    nvvidconv.set_property("compute-hw", 1)  # Use VIC (JetPack 6.2 workaround)

    caps_rgba = Gst.ElementFactory.make("capsfilter", "caps_rgba")
    caps_rgba.set_property(
        "caps",
        Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA"),
    )

    # Output queue with leaky for downstream protection
    queue_out = Gst.ElementFactory.make("queue", "queue_out")
    queue_out.set_property("max-size-buffers", 2)
    queue_out.set_property("max-size-bytes", 0)
    queue_out.set_property("max-size-time", 0)
    queue_out.set_property("leaky", 2)  # Drop oldest if full

    appsink = Gst.ElementFactory.make("appsink", "appsink")
    if not appsink:
        raise RuntimeError("Failed to create appsink element")
    appsink.set_property("emit-signals", True)
    appsink.set_property("sync", False)
    appsink.set_property("max-buffers", 1)
    appsink.set_property("drop", True)

    elements = [
        udpsrc,
        queue_src,
        caps_rtp,
        rtph264depay,
        h264parse,
        decoder,
        nvvidconv,
        caps_rgba,
        queue_out,
        appsink,
    ]

    for elem in elements:
        pipeline.add(elem)

    # Link all elements in sequence
    for i in range(len(elements) - 1):
        if not elements[i].link(elements[i + 1]):
            raise RuntimeError(
                f"Failed to link {elements[i].get_name()} -> {elements[i + 1].get_name()}"
            )

    return pipeline, appsink


def main():
    parser = argparse.ArgumentParser(description="UDP H264 passthrough to raw JPEG UDP")
    parser.add_argument(
        "--udp-source",
        default="230.1.1.1:1720",
        help="Multicast address:port for H264 input stream (default: 230.1.1.1:1720)",
    )
    parser.add_argument(
        "--multicast-iface",
        default="",
        help="Network interface for multicast (e.g., enP8p1s0)",
    )
    parser.add_argument(
        "--out-host",
        default="127.0.0.1",
        help="Destination host for raw JPEG output (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--out-port",
        type=int,
        default=DEFAULT_OUTPUT_PORT,
        help=f"Destination port for raw JPEG output (default: {DEFAULT_OUTPUT_PORT})",
    )
    parser.add_argument(
        "--jpeg-qual",
        type=int,
        default=80,
        help="JPEG quality 1-100 (default: 80)",
    )
    args = parser.parse_args()

    # Parse UDP source address:port
    if ":" in args.udp_source:
        addr, port = args.udp_source.rsplit(":", 1)
        udp_address, udp_port = addr, int(port)
    else:
        udp_address, udp_port = args.udp_source, DEFAULT_UDP_H264_PORT

    # Create sender
    sender = RawFrameSender(
        args.out_host, args.out_port, UDP_CHUNK_SIZE, args.jpeg_qual
    )

    # Build pipeline
    try:
        pipeline, appsink = build_pipeline(udp_address, udp_port, args.multicast_iface)
    except RuntimeError as e:
        print(f"Error building pipeline: {e}", file=sys.stderr)
        sys.exit(1)

    frame_count = [0]

    def on_new_sample(sink, _user_data):
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.OK

        buffer = sample.get_buffer()
        if buffer is None:
            return Gst.FlowReturn.OK

        caps = sample.get_caps()
        s = caps.get_structure(0)
        width = s.get_value("width")
        height = s.get_value("height")

        # Map GPU surface and copy to CPU
        try:
            surface = pyds.get_nvds_buf_surface(hash(buffer), 0)
            frame_rgba = np.array(surface, copy=True, order="C").reshape(
                (height, width, 4)
            )
        except Exception as e:
            print(f"Frame copy error: {e}", file=sys.stderr)
            return Gst.FlowReturn.OK

        # Release GPU buffer immediately
        del surface, buffer, sample

        # Convert RGBA to BGR and send
        frame_bgr = cv2.cvtColor(frame_rgba, cv2.COLOR_RGBA2BGR)
        sender.send_frame(frame_bgr)

        frame_count[0] += 1
        if frame_count[0] % 100 == 0:
            print(f"Sent {frame_count[0]} frames", flush=True)

        return Gst.FlowReturn.OK

    appsink.connect("new-sample", on_new_sample, None)

    # Bus handler for errors/EOS
    loop = GLib.MainLoop()
    bus = pipeline.get_bus()
    bus.add_signal_watch()

    def on_message(_bus, message, loop):
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"ERROR: {err}", file=sys.stderr)
            if debug:
                print(f"DEBUG: {debug}", file=sys.stderr)
            loop.quit()
        elif message.type == Gst.MessageType.EOS:
            print("EOS received")
            loop.quit()

    bus.connect("message", on_message, loop)

    # Clean shutdown on signals
    def on_signal():
        print("\nShutting down...")
        loop.quit()
        return GLib.SOURCE_REMOVE

    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGINT, on_signal)
    GLib.unix_signal_add(GLib.PRIORITY_HIGH, signal.SIGTERM, on_signal)

    # Start pipeline
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("Failed to start pipeline", file=sys.stderr)
        sys.exit(1)

    print(
        f"Running: UDP {udp_address}:{udp_port} → JPEG → {args.out_host}:{args.out_port}"
    )
    if args.multicast_iface:
        print(f"Multicast interface: {args.multicast_iface}")
    print("Press Ctrl+C to stop.")

    try:
        loop.run()
    finally:
        bus.remove_signal_watch()
        pipeline.set_state(Gst.State.NULL)
        print("Done.")


if __name__ == "__main__":
    main()
