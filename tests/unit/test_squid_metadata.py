"""Tests for the shared Squid metadata helper."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from squid_tools.core.readers._squid_metadata import (
    load_yaml_and_json,
    parse_channels_from_xml,
)


def _write_xml(path: Path, body: str) -> None:
    path.write_text(f"<modes>\n{body}\n</modes>\n")


class TestParseChannelsFromXml:
    def test_selected_only(self, tmp_path: Path) -> None:
        xml = tmp_path / "configurations.xml"
        _write_xml(xml, """
            <mode ID="5" Name="Fluorescence 405 nm Ex"
                  ExposureTime="50.0" IlluminationSource="11"
                  IlluminationIntensity="21.0" ZOffset="0.0"
                  Selected="true">2141688</mode>
            <mode ID="1" Name="BF LED matrix full"
                  ExposureTime="12.0" IlluminationSource="0"
                  IlluminationIntensity="5.0" ZOffset="0.0"
                  Selected="false">16777215</mode>
            <mode ID="6" Name="Fluorescence 488 nm Ex"
                  ExposureTime="25.0" IlluminationSource="12"
                  IlluminationIntensity="27.0" ZOffset="0.0"
                  Selected="true">2096896</mode>
        """)
        channels = parse_channels_from_xml(xml)
        assert [c.name for c in channels] == [
            "Fluorescence 405 nm Ex",
            "Fluorescence 488 nm Ex",
        ]
        assert channels[0].exposure_time_ms == pytest.approx(50.0)
        assert channels[0].illumination_intensity == pytest.approx(21.0)
        assert channels[0].illumination_source == "11"

    def test_no_selected_modes(self, tmp_path: Path) -> None:
        xml = tmp_path / "configurations.xml"
        _write_xml(xml, """
            <mode ID="1" Name="Off" ExposureTime="0"
                  IlluminationSource="0" IlluminationIntensity="0"
                  Selected="false">0</mode>
        """)
        assert parse_channels_from_xml(xml) == []

    def test_missing_zoffset_defaults_to_zero(self, tmp_path: Path) -> None:
        xml = tmp_path / "configurations.xml"
        _write_xml(xml, """
            <mode ID="5" Name="Fluorescence 405 nm Ex"
                  ExposureTime="50" IlluminationSource="11"
                  IlluminationIntensity="21" Selected="true">0</mode>
        """)
        channels = parse_channels_from_xml(xml)
        assert channels[0].z_offset_um == 0.0


class TestLoadYamlAndJson:
    def test_yaml_only(self, tmp_path: Path) -> None:
        (tmp_path / "acquisition.yaml").write_text("objective:\n  name: 10x\n")
        yaml_meta, json_params = load_yaml_and_json(tmp_path)
        assert yaml_meta == {"objective": {"name": "10x"}}
        assert json_params == {}

    def test_json_only(self, tmp_path: Path) -> None:
        (tmp_path / "acquisition parameters.json").write_text(
            json.dumps({"Nz": 10, "dz(um)": 1.5}),
        )
        yaml_meta, json_params = load_yaml_and_json(tmp_path)
        assert yaml_meta == {}
        assert json_params == {"Nz": 10, "dz(um)": 1.5}

    def test_both(self, tmp_path: Path) -> None:
        (tmp_path / "acquisition.yaml").write_text("channels:\n  - name: ch0\n")
        (tmp_path / "acquisition parameters.json").write_text(
            json.dumps({"Nz": 5}),
        )
        yaml_meta, json_params = load_yaml_and_json(tmp_path)
        assert yaml_meta == {"channels": [{"name": "ch0"}]}
        assert json_params == {"Nz": 5}

    def test_neither(self, tmp_path: Path) -> None:
        yaml_meta, json_params = load_yaml_and_json(tmp_path)
        assert yaml_meta == {}
        assert json_params == {}
