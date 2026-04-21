"""Phase-from-defocus plugin (parameter surface + stub reconstruction).

Absorbed from Cephla-Lab/phase_from_defocus (waveorder-based). v1 ships
the parameter surface + manifest, plus a stub `process()` that returns
the input unchanged when a z-stack is not available or when waveorder
is not installed. The real reconstruction needs the full z-stack and
is wired into ViewerWidget's 3D path in v2.

Source repo: https://github.com/Cephla-Lab/phase_from_defocus
Source GUI:  src/phasedefocus/core.py (PhaseReconstructor class)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from squid_tools.core.data_model import Acquisition, OpticalMetadata
from squid_tools.processing.base import ProcessingPlugin

logger = logging.getLogger(__name__)


class PhaseFromDefocusParams(BaseModel):
    """Parameter surface mirroring PhaseReconstructor's __init__."""

    wavelength_um: float = Field(default=0.520)
    illumination_na_ratio: float = Field(default=0.87)
    index_of_refraction_media: float = Field(default=1.0)
    regularization_strength: float = Field(default=0.0)
    autotune_regularization: bool = Field(default=True)


class PhaseFromDefocusPlugin(ProcessingPlugin):
    """Phase-from-defocus reconstruction.

    Per the spec, v1 plugin surface captures parameters; real 3D
    reconstruction wires in during v2 (needs waveorder + a z-stack
    fetched through engine.get_volume).
    """

    name: str = "Phase from Defocus"
    category: str = "phase"
    requires_gpu: bool = False
    _warned_stub: bool = False

    def parameters(self) -> type[BaseModel]:
        return PhaseFromDefocusParams

    def validate(self, acq: Acquisition) -> list[str]:
        warnings: list[str] = []
        if acq.z_stack is None or acq.z_stack.nz < 3:
            warnings.append(
                "Phase-from-defocus needs a z-stack (≥3 planes); "
                "this acquisition doesn't qualify.",
            )
        try:
            import waveorder  # noqa: F401
        except ImportError:
            warnings.append(
                "waveorder not installed; plugin will passthrough. "
                "`pip install waveorder` to enable reconstruction.",
            )
        return warnings

    def default_params(
        self, optical: OpticalMetadata | None = None,
    ) -> BaseModel:
        if optical is None:
            return PhaseFromDefocusParams()
        kwargs: dict[str, Any] = {}
        if optical.immersion_ri:
            kwargs["index_of_refraction_media"] = float(optical.immersion_ri)
        return PhaseFromDefocusParams(**kwargs)

    def process(
        self, frame: np.ndarray, params: BaseModel,
    ) -> np.ndarray:
        """v1 stub: single-frame processing returns input unchanged.

        Phase-from-defocus is inherently z-stack-based; the viewer uses
        this plugin via future v2 `run_live` on the engine's volumes.
        """
        if not PhaseFromDefocusPlugin._warned_stub:
            logger.warning(
                "Phase-from-defocus plugin is a v1 stub "
                "(returns input unchanged). Real reconstruction lands in v2.",
            )
            PhaseFromDefocusPlugin._warned_stub = True
        return frame

    def test_cases(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "stub_passthrough",
                "input": np.zeros((16, 16), dtype=np.float32),
                "params": {},
            },
        ]
