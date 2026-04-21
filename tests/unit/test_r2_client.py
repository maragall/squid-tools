"""Tests for R2Client (boto3 S3 mocked)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_boto3():
    """Patch boto3.client and botocore.config.Config, yield the fake S3 client."""
    fake_s3 = MagicMock()
    with patch("boto3.client", return_value=fake_s3) as mock_client, patch(
        "botocore.config.Config",
    ):
        yield mock_client, fake_s3


class TestR2ClientConstruction:
    def test_endpoint_url_includes_account_id(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        mock_client, _ = fake_boto3
        R2Client("acct123", "AKID", "SECRET", "bucket")
        kwargs = mock_client.call_args.kwargs
        assert kwargs["endpoint_url"] == "https://acct123.r2.cloudflarestorage.com"
        assert kwargs["aws_access_key_id"] == "AKID"
        assert kwargs["aws_secret_access_key"] == "SECRET"
        assert kwargs["region_name"] == "auto"
        mock_client.assert_called_once()
        assert mock_client.call_args.args[0] == "s3"

    def test_default_region_is_auto(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        mock_client, _ = fake_boto3
        R2Client("a", "b", "c", "d")
        assert mock_client.call_args.kwargs["region_name"] == "auto"


class TestR2ClientFromEnv:
    def test_missing_env_vars_raises(
        self, fake_boto3, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        for k in (
            "CF_R2_ACCOUNT_ID",
            "CF_R2_ACCESS_KEY_ID",
            "CF_R2_SECRET_ACCESS_KEY",
            "CF_R2_BUCKET",
        ):
            monkeypatch.delenv(k, raising=False)
        with pytest.raises(RuntimeError, match="Missing R2 env vars"):
            R2Client.from_env()

    def test_from_env_constructs_when_all_set(
        self, fake_boto3, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        monkeypatch.setenv("CF_R2_ACCOUNT_ID", "a")
        monkeypatch.setenv("CF_R2_ACCESS_KEY_ID", "b")
        monkeypatch.setenv("CF_R2_SECRET_ACCESS_KEY", "c")
        monkeypatch.setenv("CF_R2_BUCKET", "d")
        client = R2Client.from_env()
        assert client._bucket == "d"

    def test_from_env_lists_specific_missing_vars(
        self, fake_boto3, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        monkeypatch.setenv("CF_R2_ACCOUNT_ID", "a")
        monkeypatch.setenv("CF_R2_ACCESS_KEY_ID", "b")
        monkeypatch.delenv("CF_R2_SECRET_ACCESS_KEY", raising=False)
        monkeypatch.delenv("CF_R2_BUCKET", raising=False)
        with pytest.raises(RuntimeError) as exc:
            R2Client.from_env()
        msg = str(exc.value)
        assert "CF_R2_SECRET_ACCESS_KEY" in msg
        assert "CF_R2_BUCKET" in msg
        assert "CF_R2_ACCOUNT_ID" not in msg


class TestUploadFile:
    def test_upload_file_calls_s3_upload(self, fake_boto3, tmp_path: Path) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        local = tmp_path / "a.txt"
        local.write_text("hi")
        client = R2Client("a", "b", "c", "bucket")
        client.upload_file(local, "prefix/a.txt")
        fake_s3.upload_file.assert_called_once_with(
            str(local), "bucket", "prefix/a.txt",
        )


class TestUploadDir:
    def test_upload_dir_walks_recursively(
        self, fake_boto3, tmp_path: Path,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        root = tmp_path / "acq"
        root.mkdir()
        (root / "acquisition.yaml").write_text("x")
        (root / "ome_tiff").mkdir()
        (root / "ome_tiff" / "0_0.ome.tiff").write_text("y")
        (root / "ome_tiff" / "0_1.ome.tiff").write_text("z")

        client = R2Client("a", "b", "c", "bucket")
        keys = client.upload_dir(root, "demo")

        assert set(keys) == {
            "demo/acquisition.yaml",
            "demo/ome_tiff/0_0.ome.tiff",
            "demo/ome_tiff/0_1.ome.tiff",
        }
        assert fake_s3.upload_file.call_count == 3

    def test_upload_dir_strips_trailing_slash_from_prefix(
        self, fake_boto3, tmp_path: Path,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        root = tmp_path / "acq"
        root.mkdir()
        (root / "a.txt").write_text("x")

        client = R2Client("a", "b", "c", "bucket")
        keys = client.upload_dir(root, "demo/")
        assert keys == ["demo/a.txt"]

    def test_upload_dir_on_file_raises(
        self, fake_boto3, tmp_path: Path,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        file_path = tmp_path / "a.txt"
        file_path.write_text("x")
        client = R2Client("a", "b", "c", "bucket")
        with pytest.raises(ValueError, match="not a directory"):
            client.upload_dir(file_path, "demo")


class TestListKeys:
    def test_list_keys_paginates(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        paginator = MagicMock()
        paginator.paginate.return_value = [
            {"Contents": [{"Key": "a"}, {"Key": "b"}]},
            {"Contents": [{"Key": "c"}]},
        ]
        fake_s3.get_paginator.return_value = paginator

        client = R2Client("a", "b", "c", "bucket")
        keys = client.list_keys("prefix")
        assert keys == ["a", "b", "c"]
        fake_s3.get_paginator.assert_called_once_with("list_objects_v2")

    def test_list_keys_empty_returns_empty(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        paginator = MagicMock()
        paginator.paginate.return_value = [{}]
        fake_s3.get_paginator.return_value = paginator
        client = R2Client("a", "b", "c", "bucket")
        assert client.list_keys("prefix") == []


class TestDownloadFile:
    def test_download_creates_parent_dirs(
        self, fake_boto3, tmp_path: Path,
    ) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        target = tmp_path / "sub" / "deep" / "out.txt"
        client = R2Client("a", "b", "c", "bucket")
        client.download_file("some/key", target)
        fake_s3.download_file.assert_called_once_with(
            "bucket", "some/key", str(target),
        )
        assert target.parent.is_dir()


class TestKeyExists:
    def test_key_exists_true(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        fake_s3.head_object.return_value = {"ContentLength": 0}
        client = R2Client("a", "b", "c", "bucket")
        assert client.key_exists("k") is True

    def test_key_exists_false_on_exception(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        fake_s3.head_object.side_effect = Exception("404")
        client = R2Client("a", "b", "c", "bucket")
        assert client.key_exists("k") is False


class TestPresignedGetUrl:
    def test_generates_url(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        fake_s3.generate_presigned_url.return_value = "https://example"
        client = R2Client("a", "b", "c", "bucket")
        url = client.presigned_get_url("some/key", expires_in=120)
        assert url == "https://example"
        fake_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "bucket", "Key": "some/key"},
            ExpiresIn=120,
        )

    def test_default_expiry_is_3600(self, fake_boto3) -> None:
        from squid_tools.remote.r2_client import R2Client

        _, fake_s3 = fake_boto3
        fake_s3.generate_presigned_url.return_value = "u"
        client = R2Client("a", "b", "c", "bucket")
        client.presigned_get_url("k")
        assert fake_s3.generate_presigned_url.call_args.kwargs[
            "ExpiresIn"
        ] == 3600
