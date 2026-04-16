"""Tests for GPU runtime detection."""

from squid_tools.core.gpu import GPUInfo, detect_gpu


class TestGPUDetection:
    def test_returns_gpu_info(self) -> None:
        info = detect_gpu()
        assert isinstance(info, GPUInfo)

    def test_has_available_field(self) -> None:
        info = detect_gpu()
        assert isinstance(info.available, bool)

    def test_has_name_field(self) -> None:
        info = detect_gpu()
        assert isinstance(info.name, str)

    def test_has_backend_field(self) -> None:
        info = detect_gpu()
        assert info.backend in ("cupy", "none")

    def test_cpu_fallback_message(self) -> None:
        info = detect_gpu()
        if not info.available:
            assert "CPU" in info.name or "cpu" in info.name.lower() or info.name == "CPU only"
