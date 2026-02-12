"""Thin wrapper around Unitree SDK clients used by the helper."""

from __future__ import annotations

import logging
from collections.abc import Callable

from unitree_sdk2py.core.channel import ChannelFactoryInitialize
from unitree_sdk2py.go2.obstacles_avoid.obstacles_avoid_client import (
    ObstaclesAvoidClient,
)
from unitree_sdk2py.go2.sport.sport_api import (
    SPORT_API_ID_DAMP,
    SPORT_API_ID_STOPMOVE,
)
from unitree_sdk2py.go2.sport.sport_client import SportClient

from .pal_vui_client import PalVuiClient


def initialize_unitree_dds(dds_profile: str | None) -> None:
    """Initialize CycloneDDS domain used by Unitree SDK ahead of time."""
    if ChannelFactoryInitialize is None:
        return
    try:
        if dds_profile:
            ChannelFactoryInitialize(0, dds_profile)
        else:
            ChannelFactoryInitialize(0)
    except Exception:
        # Domain conflicts or duplicate initialization attempts are benign.
        pass


class _PrioritySportClient(SportClient):
    """SportClient that re-registers stop APIs with higher priority."""

    def Init(self) -> None:  # pragma: no cover - SDK only
        super().Init()
        try:
            self._RegistApi(SPORT_API_ID_DAMP, 1)
            self._RegistApi(SPORT_API_ID_STOPMOVE, 1)
        except Exception as exc:
            # Best-effort; fall back to default priority if this fails.
            import sys

            print(
                f"Warning: Failed to set high-priority stop APIs: {exc}",
                file=sys.stderr,
            )


class PalAdapter:
    """Encapsulates direct SDK access (SportClient + AvoidClient)."""

    def __init__(
        self,
        *,
        network_interface: str | None = None,
        timeout: float = 1.0,
        sport_client: SportClient | None = None,
        avoid_client: ObstaclesAvoidClient | None = None,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.network_interface = network_interface
        self.timeout = timeout
        self._logger = log_fn or logging.getLogger(__name__).info

        self._ensure_dds_initialized()

        self.sport_client = sport_client or self._init_sport_client()
        self.avoid_client = avoid_client or self._init_avoid_client()
        self.vui_client = self._init_vui_client()

    def _log(self, message: str) -> None:
        if self._logger:
            self._logger(message)

    def _ensure_dds_initialized(self) -> None:
        if ChannelFactoryInitialize is None:
            return
        try:
            if self.network_interface:
                ChannelFactoryInitialize(0, self.network_interface)
            else:
                ChannelFactoryInitialize(0)
        except Exception:
            self._log("[UnitreeAdapter] ChannelFactory initialization failed")

    def _init_sport_client(self) -> SportClient | None:
        try:
            self._ensure_dds_initialized()
            client = _PrioritySportClient()
            client.SetTimeout(self.timeout)
            client.Init()
            self._log("[UnitreeAdapter] sport_client initialized")
            return client
        except Exception as exc:
            self._log(f"[UnitreeAdapter] sport_client init failed: {exc}")
            return None

    def _init_avoid_client(self) -> ObstaclesAvoidClient | None:
        try:
            self._ensure_dds_initialized()
            client = ObstaclesAvoidClient()
            client.SetTimeout(self.timeout)
            client.Init()
            self._log("[UnitreeAdapter] avoid_client initialized")
            return client
        except Exception as exc:
            self._log(f"[UnitreeAdapter] avoid_client init failed: {exc}")
            return None

    def _init_vui_client(self) -> PalVuiClient | None:
        try:
            self._ensure_dds_initialized()
            client = PalVuiClient()
            client.SetTimeout(self.timeout)
            client.Init()
            self._log("[UnitreeAdapter] vui_client initialized")
            return client
        except Exception as exc:
            self._log(f"[UnitreeAdapter] vui_client init failed: {exc}")
            return None


__all__ = ["PalAdapter", "initialize_unitree_dds"]
