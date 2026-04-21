"""End-to-end integration test: open acquisition, view data, run processing."""

from pathlib import Path

import numpy as np
from pytestqt.qtbot import QtBot

from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestEndToEnd:
    def test_open_view_process(self, qtbot: QtBot, tmp_path: Path) -> None:
        """Full cycle: open acquisition, select region, run background subtraction."""
        from squid_tools.gui.app import MainWindow

        # Create test acquisition
        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )

        # Launch window
        window = MainWindow()
        qtbot.addWidget(window)

        # Open acquisition
        window.open_acquisition(acq_path)
        assert window.controller.acquisition is not None
        assert window.region_selector.selected_region_id() == "0"

        # Verify controller can get frame
        frame = window.controller.get_frame(region="0", fov=0)
        assert frame.shape == (128, 128)

        # Run flatfield correction
        result = window.controller.run_plugin("Flatfield (BaSiC)", frame.astype(np.float64))
        assert result.shape == (128, 128)

        # Log should show status
        assert "Loaded" in window.log_panel.status_text()

        window.close()
