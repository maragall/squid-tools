"""Tests for Cephla channel colormap mapping."""

from squid_tools.viewer.colormaps import CHANNEL_COLORS, get_channel_colormap


class TestChannelColormaps:
    def test_405_is_blues(self) -> None:
        assert get_channel_colormap("Fluorescence_405_nm_Ex") == "blues"

    def test_488_is_greens(self) -> None:
        assert get_channel_colormap("Fluorescence_488_nm_Ex") == "greens"

    def test_561_is_autumn(self) -> None:
        assert get_channel_colormap("Fluorescence_561_nm_Ex") == "autumn"

    def test_638_is_reds(self) -> None:
        assert get_channel_colormap("Fluorescence_638_nm_Ex") == "reds"

    def test_730_is_reds(self) -> None:
        assert get_channel_colormap("Fluorescence_730_nm_Ex") == "reds"

    def test_unknown_is_grays(self) -> None:
        assert get_channel_colormap("BF_LED_matrix_full") == "grays"

    def test_channel_colors_hex(self) -> None:
        assert CHANNEL_COLORS["405"] == "#0000FF"
        assert CHANNEL_COLORS["488"] == "#00FF00"
        assert CHANNEL_COLORS["561"] == "#FFCF00"
        assert CHANNEL_COLORS["638"] == "#FF0000"
