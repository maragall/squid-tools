"""Cloudflare R2 (S3-compatible) client for squid-tools."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

logger = logging.getLogger(__name__)


class R2Client:
    """Thin wrapper around boto3 S3 client configured for Cloudflare R2."""

    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        *,
        region: str = "auto",
    ) -> None:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as e:
            raise RuntimeError(
                "R2Client requires boto3; install with `pip install boto3`",
            ) from e

        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = bucket
        self._endpoint_url = endpoint_url

    @classmethod
    def from_env(cls) -> R2Client:
        """Construct from CF_R2_* environment variables."""
        required = [
            "CF_R2_ACCOUNT_ID",
            "CF_R2_ACCESS_KEY_ID",
            "CF_R2_SECRET_ACCESS_KEY",
            "CF_R2_BUCKET",
        ]
        missing = [k for k in required if not os.environ.get(k)]
        if missing:
            raise RuntimeError(
                f"Missing R2 env vars: {', '.join(missing)}",
            )
        return cls(
            account_id=os.environ["CF_R2_ACCOUNT_ID"],
            access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
            secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"],
            bucket=os.environ["CF_R2_BUCKET"],
        )

    def upload_file(self, local_path: Path, key: str) -> None:
        """Upload a single file to the bucket at the given key."""
        self._s3.upload_file(str(local_path), self._bucket, key)
        logger.info("uploaded %s -> %s/%s", local_path, self._bucket, key)

    def upload_dir(
        self, local_dir: Path, prefix: str,
    ) -> list[str]:
        """Upload every file under local_dir, preserving structure.

        Each key is `<prefix>/<relative_posix_path>`. Returns the list
        of uploaded keys.
        """
        if not local_dir.is_dir():
            raise ValueError(f"{local_dir} is not a directory")
        uploaded: list[str] = []
        for file in _iter_files(local_dir):
            rel = file.relative_to(local_dir).as_posix()
            key = f"{prefix.rstrip('/')}/{rel}"
            self.upload_file(file, key)
            uploaded.append(key)
        logger.info(
            "upload_dir complete: %d files under prefix %s",
            len(uploaded), prefix,
        )
        return uploaded

    def list_keys(self, prefix: str) -> list[str]:
        """Return keys matching the given prefix."""
        paginator = self._s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def download_file(self, key: str, local_path: Path) -> None:
        """Download a key to a local path (creates parent dirs)."""
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._s3.download_file(self._bucket, key, str(local_path))
        logger.info("downloaded %s/%s -> %s", self._bucket, key, local_path)

    def key_exists(self, key: str) -> bool:
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str:
        """Return a presigned GET URL valid for `expires_in` seconds."""
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def _iter_files(root: Path) -> Iterator[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path
