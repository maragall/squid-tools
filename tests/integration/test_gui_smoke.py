"""Smoke tests for the main GUI window."""

from pathlib import Path

from pytestqt.qtbot import QtBot

from tests.fixtures.generate_fixtures import create_individual_acquisition


class TestMainWindowSmoke:
    def test_main_window_instantiates(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        assert window is not None
        assert window.windowTitle() == "Squid-Tools"

    def test_main_window_has_panels(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        assert window.controls_panel is not None
        assert window.region_selector is not None
        assert window.processing_tabs is not None
        assert window.log_panel is not None

    def test_embeddable_widget(self, qtbot: QtBot) -> None:
        from squid_tools.gui.embed import SquidToolsWidget

        widget = SquidToolsWidget()
        qtbot.addWidget(widget)
        assert widget is not None


class TestMainWindowDataLoading:
    def test_has_open_action(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        # Should have a File menu with Open action
        menu_bar = window.menuBar()
        file_menu = None
        for action in menu_bar.actions():
            if action.text() == "&File":
                file_menu = action.menu()
        assert file_menu is not None

    def test_load_acquisition_populates_selector(self, qtbot: QtBot, tmp_path: Path) -> None:
        from squid_tools.gui.app import MainWindow

        acq_path = create_individual_acquisition(
            tmp_path / "acq", nx=2, ny=2, nz=1, nc=1, nt=1
        )
        window = MainWindow()
        qtbot.addWidget(window)
        window.open_acquisition(acq_path)
        region_id = window.region_selector.selected_region_id()
        regions = window.controller.acquisition.regions
        assert region_id is not None or len(regions) > 0


class TestPluginsRegistered:
    def test_default_plugins_loaded(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        names = window.controller.registry.list_names()
        assert "Flatfield Correction" in names

    def test_processing_tabs_have_plugins(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        assert window.processing_tabs.count() >= 1


class TestStitcherRegistered:
    def test_stitcher_in_registry(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        names = window.controller.registry.list_names()
        assert "Stitcher" in names

    def test_processing_tabs_has_stitcher(self, qtbot: QtBot) -> None:
        from squid_tools.gui.app import MainWindow

        window = MainWindow()
        qtbot.addWidget(window)
        tab_names = [
            window.processing_tabs.tabText(i)
            for i in range(window.processing_tabs.count())
        ]
        assert "Stitcher" in tab_names
