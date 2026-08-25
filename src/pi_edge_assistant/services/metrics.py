from __future__ import annotations

from pathlib import Path
from typing import Any

import psutil


class MetricsService:
    THERMAL_PATHS = (
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/devices/virtual/thermal/thermal_zone0/temp"),
    )

    def snapshot(self) -> dict[str, Any]:
        memory = self._safe_call(psutil.virtual_memory)
        swap = self._safe_call(psutil.swap_memory)
        disk = self._safe_call(psutil.disk_usage, "/")
        return {
            "cpu_percent": self._safe_call(psutil.cpu_percent, interval=None),
            "memory_used_mb": round(memory.used / 1024 / 1024, 1) if memory else None,
            "memory_percent": memory.percent if memory else None,
            "swap_used_mb": round(swap.used / 1024 / 1024, 1) if swap else None,
            "swap_percent": swap.percent if swap else None,
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 1) if disk else None,
            "temperature_c": self.temperature(),
        }

    @staticmethod
    def _safe_call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (OSError, RuntimeError):
            return None

    def temperature(self) -> float | None:
        for path in self.THERMAL_PATHS:
            try:
                return round(float(path.read_text().strip()) / 1000, 1)
            except (OSError, ValueError):
                continue
        return None
