"""Tests for the GUI manifest loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_tools.core.gui_manifest import (
    GuiManifest,
    GuiParameter,
    load_manifest,
    manifest_path_for,
)


class TestLoadManifest:
    def test_returns_none_when_no_manifest(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "plugin.py"
        plugin_file.write_text("# stub")
        assert load_manifest(plugin_file) is None

    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "plugin.py"
        plugin_file.write_text("# stub")
        manifest_file = tmp_path / "gui_manifest.yaml"
        manifest_file.write_text(
            "name: Foo\n"
            "source_repo: https://example.com\n"
            "notes: Defaults from Cephla 10x calibration.\n"
            "parameters:\n"
            "  alpha:\n"
            "    default: 0.5\n"
            "    visible: true\n"
            "    tooltip: Alpha smoothing factor.\n"
            "    min: 0.0\n"
            "    max: 1.0\n"
            "    step: 0.01\n"
            "  hidden_debug_flag:\n"
            "    default: false\n"
            "    visible: false\n",
        )
        manifest = load_manifest(plugin_file)
        assert manifest is not None
        assert manifest.name == "Foo"
        assert manifest.source_repo == "https://example.com"
        assert "Cephla" in manifest.notes
        assert "alpha" in manifest.parameters
        alpha = manifest.parameters["alpha"]
        assert alpha.default == 0.5
        assert alpha.visible is True
        assert alpha.min == 0.0
        assert alpha.max == 1.0
        hidden = manifest.parameters["hidden_debug_flag"]
        assert hidden.visible is False

    def test_empty_manifest_returns_none(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "plugin.py"
        plugin_file.write_text("# stub")
        manifest_file = tmp_path / "gui_manifest.yaml"
        manifest_file.write_text("")
        assert load_manifest(plugin_file) is None

    def test_stitcher_manifest_loads(self) -> None:
        """The real stitcher manifest that ships with v1 must parse."""
        from squid_tools.processing.stitching import plugin as stitcher_plugin

        manifest = load_manifest(stitcher_plugin.__file__)
        assert manifest is not None
        assert manifest.name == "Stitcher"
        assert "pixel_size_um" in manifest.parameters


class TestManifestPathFor:
    def test_returns_sibling_yaml(self, tmp_path: Path) -> None:
        plugin_file = tmp_path / "sub" / "plugin.py"
        plugin_file.parent.mkdir()
        plugin_file.write_text("x")
        assert manifest_path_for(plugin_file) == tmp_path / "sub" / "gui_manifest.yaml"


class TestGuiParameter:
    def test_required_field_is_only_name(self) -> None:
        # All fields have defaults; creation with no args should work.
        p = GuiParameter()
        assert p.visible is True
        assert p.tooltip == ""

    def test_construct_with_override(self) -> None:
        p = GuiParameter(default=1.5, visible=False, tooltip="hi", min=0, max=2)
        assert p.default == 1.5
        assert p.visible is False
        assert p.min == 0

    def test_invalid_payload_raises(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            GuiManifest.model_validate({"name": 42, "parameters": "not a dict"})
