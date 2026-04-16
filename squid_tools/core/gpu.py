"""GPU runtime detection.

Detects CUDA GPU via CuPy at runtime. Falls back to CPU silently.
No build-time CUDA dependency required.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GPUInfo:
    """GPU detection result."""

    available: bool
    name: str
    backend: str  # "cupy" or "none"
    device_id: int = 0


def detect_gpu() -> GPUInfo:
    """Detect GPU at runtime. Returns GPUInfo with CPU fallback.

    Tries CuPy first. If not installed or no CUDA device, returns
    CPU-only info. Never raises.
    """
    try:
        import cupy  # noqa: PLC0415

        props = cupy.cuda.runtime.getDeviceProperties(0)
        name = props["name"].decode() if isinstance(props["name"], bytes) else str(props["name"])
        return GPUInfo(available=True, name=name, backend="cupy", device_id=0)
    except Exception:
        pass

    return GPUInfo(available=False, name="CPU only", backend="none")
