"""Mock implementation of FrameClient for testing without DeepStream."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class MockFrameClient:
    """
    Mock FrameClient that loads images from a directory and rotates through them.

    Each call to get_frame() returns the next image in sequence, simulating
    camera movement during patrol.
    """

    def __init__(
        self,
        images_dir: str | Path,
        *,
        host: str = "127.0.0.1",  # Ignored, for API compatibility
        port: int = 5010,  # Ignored, for API compatibility
        timeout: float = 1.0,  # Ignored, for API compatibility
    ) -> None:
        _ = host, port, timeout  # Unused in mock
        self._images_dir = Path(images_dir)
        self._images: list[Path] = []
        self._current_index: int = 0
        self._started: bool = False

    def start(self) -> None:
        """Load images from directory."""
        if self._started:
            return

        if not self._images_dir.exists():
            raise FileNotFoundError(f"Images directory not found: {self._images_dir}")

        # Load all image files, sorted for deterministic order
        self._images = sorted(
            p
            for p in self._images_dir.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
        )

        if not self._images:
            raise FileNotFoundError(
                f"No images found in {self._images_dir} "
                f"(supported: {', '.join(IMAGE_EXTENSIONS)})"
            )

        self._current_index = 0
        self._started = True

    def stop(self) -> None:
        """Clean up (no-op for mock)."""
        self._started = False

    def get_frame(self, max_age_sec: float = 2.0) -> Optional[bytes]:
        """
        Get the next image in rotation.

        Args:
            max_age_sec: Ignored in mock (always returns fresh frame)

        Returns:
            JPEG/PNG bytes or None if not started
        """
        _ = max_age_sec  # Unused in mock

        if not self._started or not self._images:
            return None

        # Get current image
        image_path = self._images[self._current_index]

        # Rotate to next image
        self._current_index = (self._current_index + 1) % len(self._images)

        # Read and return image bytes
        return image_path.read_bytes()

    def __enter__(self) -> "MockFrameClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


__all__ = ["MockFrameClient"]
