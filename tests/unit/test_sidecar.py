"""Tests for OME sidecar manifest."""

from pathlib import Path

from squid_tools.core.sidecar import ProcessingRun, SidecarManifest


class TestSidecarManifest:
    def test_create_empty_manifest(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        assert len(manifest.runs) == 0

    def test_add_run(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        run = ProcessingRun(
            plugin="TileFusion Stitcher",
            version="0.3.1",
            params={"overlap_percent": 15},
            output_path="stitcher/",
        )
        manifest.add_run(run)
        assert len(manifest.runs) == 1
        assert manifest.runs[0].plugin == "TileFusion Stitcher"

    def test_save_and_load(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        manifest.add_run(
            ProcessingRun(
                plugin="TestPlugin",
                version="1.0",
                params={"key": "value"},
                output_path="test/",
            )
        )
        manifest.save()

        # Verify file exists
        manifest_path = tmp_path / ".squid-tools" / "manifest.json"
        assert manifest_path.exists()

        # Load and verify
        loaded = SidecarManifest.load(tmp_path)
        assert len(loaded.runs) == 1
        assert loaded.runs[0].plugin == "TestPlugin"

    def test_sidecar_dir_created(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        manifest.save()
        assert (tmp_path / ".squid-tools").is_dir()

    def test_plugin_output_dir(self, tmp_path: Path) -> None:
        manifest = SidecarManifest(acquisition_path=tmp_path)
        out_dir = manifest.plugin_output_dir("stitcher")
        assert out_dir == tmp_path / ".squid-tools" / "stitcher"
        assert out_dir.is_dir()
