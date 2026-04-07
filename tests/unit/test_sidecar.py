from squid_tools.core.sidecar import ProcessingRun, SidecarManager


def test_sidecar_creates_directory(tmp_path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    mgr.ensure_directory()
    assert (acq_path / ".squid-tools").is_dir()
    assert (acq_path / ".squid-tools" / "manifest.json").exists()


def test_sidecar_records_run(tmp_path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    mgr.ensure_directory()
    run = ProcessingRun(
        plugin="Stitcher", version="0.3.1", params={"overlap": 15}, output_path="stitcher/"
    )
    mgr.record_run(run)
    manifest = mgr.load_manifest()
    assert len(manifest["runs"]) == 1
    assert manifest["runs"][0]["plugin"] == "Stitcher"


def test_sidecar_multiple_runs(tmp_path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    mgr.ensure_directory()
    mgr.record_run(ProcessingRun(plugin="A", version="1.0", params={}, output_path="a/"))
    mgr.record_run(ProcessingRun(plugin="B", version="2.0", params={}, output_path="b/"))
    manifest = mgr.load_manifest()
    assert len(manifest["runs"]) == 2


def test_sidecar_plugin_output_dir(tmp_path):
    acq_path = tmp_path / "test_acquisition"
    acq_path.mkdir()
    mgr = SidecarManager(acq_path)
    out_dir = mgr.plugin_output_dir("stitcher")
    assert out_dir == acq_path / ".squid-tools" / "stitcher"
    assert out_dir.is_dir()
