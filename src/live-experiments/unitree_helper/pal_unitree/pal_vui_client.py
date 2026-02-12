"""VUI client with LED color control support."""

from __future__ import annotations

import json

from unitree_sdk2py.rpc.client import Client

VUI_SERVICE_NAME = "vui"
VUI_API_VERSION = "1.0.0.1"
VUI_API_ID_SET_LED = 1007


class PalVuiClient(Client):
    """VUI client with LED color support."""

    def __init__(self) -> None:
        super().__init__(VUI_SERVICE_NAME, False)

    def Init(self) -> None:
        self._SetApiVerson(VUI_API_VERSION)
        self._RegistApi(VUI_API_ID_SET_LED, 0)

    def SetLedColor(self, color: str, duration: int = 1) -> int:
        """
        Set LED color.

        Args:
            color: 'green', 'blue', 'red', 'yellow', 'purple'
            duration: How long to display (seconds) before returning to auto

        Returns:
            0 on success, error code otherwise
        """
        p = {"color": color, "time": duration}
        parameter = json.dumps(p)
        code, _ = self._Call(VUI_API_ID_SET_LED, parameter)
        return code


__all__ = ["PalVuiClient"]
