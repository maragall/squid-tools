"""Tests for Cephla-branded stylesheet."""

from squid_tools.gui.style import CEPHLA_STYLESHEET, apply_style


class TestStyle:
    def test_stylesheet_is_string(self) -> None:
        assert isinstance(CEPHLA_STYLESHEET, str)
        assert len(CEPHLA_STYLESHEET) > 100

    def test_contains_brand_colors(self) -> None:
        assert "#353535" in CEPHLA_STYLESHEET  # graphite
        assert "#2A82DA" in CEPHLA_STYLESHEET  # cephla blue
        assert "#2a2a2a" in CEPHLA_STYLESHEET  # dark graphite

    def test_apply_style_to_app(self, qtbot) -> None:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            apply_style(app)
            assert app.styleSheet() != ""
