"""
CPU and system resource detection.

Supports macOS (Apple Silicon and Intel), Linux and Windows.
"""

from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class ProcessorInfo:
    brand: str
    architecture: str
    physical_cores: int
    logical_cores: int

    def get_display_name(self) -> str:
        return f"{self.brand} ({self.logical_cores} cores, {self.architecture})"

    def get_cpu_load(self) -> Optional[float]:
        """Current system-wide CPU usage in percent, or ``None`` without psutil."""
        if psutil is not None:
            try:
                return psutil.cpu_percent(interval=None)
            except Exception:
                return None
        return None


@lru_cache(maxsize=1)
def detect_processor() -> ProcessorInfo:
    """
    Detect the CPU model, architecture and core counts.

    The result is cached: the hardware does not change while the app runs, and
    the macOS lookup spawns a subprocess that should not repeat on every dialog.
    """
    brand = ""
    system = platform.system()

    if system == "Darwin":
        # macOS: read the CPU brand string via sysctl
        try:
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="ignore").strip()
            if out:
                brand = out
        except Exception:
            pass

    if not brand and system == "Windows":
        brand = platform.processor() or os.environ.get("PROCESSOR_IDENTIFIER", "")

    if not brand and system == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "model name" in line:
                        brand = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass

    if not brand:
        brand = platform.processor() or platform.machine() or "Unknown CPU"

    architecture = platform.machine()

    logical_cores = os.cpu_count() or 1
    physical_cores = logical_cores
    if psutil is not None:
        try:
            pc = psutil.cpu_count(logical=False)
            if pc:
                physical_cores = pc
            lc = psutil.cpu_count(logical=True)
            if lc:
                logical_cores = lc
        except Exception:
            pass

    # psutil reports CPU usage relative to the previous call; the first call
    # returns a meaningless 0.0, so take it here and let later readings be real.
    if psutil is not None:
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

    return ProcessorInfo(
        brand=brand,
        architecture=architecture,
        physical_cores=physical_cores,
        logical_cores=logical_cores,
    )
