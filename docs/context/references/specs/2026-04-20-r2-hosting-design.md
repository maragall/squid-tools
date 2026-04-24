# R2 Hosting Design Spec

## Purpose

Give squid-tools the ability to push acquisitions to Cloudflare R2 (S3-compatible object storage) and pull from them for demos. This unlocks:

- Uploading a reference acquisition from the dev machine once
- Streaming that acquisition into a hosted viewer (browser demo — future cycle)
- Sharing test data across the dev + CI + web-demo nodes described in the v1 spec's "Three-node network"

This cycle lands the **hosting side only**: an R2 client + CLI script. A web demo that streams from R2 in the browser is deferred to a post-cycle follow-up.

**Audience:** Developers who want to upload data once and have it available from anywhere; downstream cycles that need presigned URLs for streaming.

**Guiding principle:** R2 is S3 with a different endpoint. The `boto3` S3 client does the work. The client wraps it with sensible defaults and a directory-upload helper, nothing more.

---

## Scope

**IN:**
- `squid_tools/remote/r2_client.py` with `R2Client(account_id, access_key_id, secret_access_key, bucket)` wrapping a `boto3` S3 client pointed at `https://<account_id>.r2.cloudflarestorage.com`
- Methods: `upload_file`, `upload_dir`, `list_keys`, `download_file`, `presigned_get_url`, `key_exists`
- `R2Client.from_env()` factory that reads credentials from env vars (`CF_R2_ACCOUNT_ID`, `CF_R2_ACCESS_KEY_ID`, `CF_R2_SECRET_ACCESS_KEY`, `CF_R2_BUCKET`)
- `scripts/upload_acquisition_to_r2.py` — CLI that uploads an acquisition directory under a given prefix
- Tests: mock boto3's S3 client; verify method calls and args
- No new runtime dependency beyond `boto3` (already installed in the dev environment); if `boto3` is not present, importing `r2_client` raises a clear error

**OUT (future cycles):**
- Browser viewer (HTML/JS streaming from R2 via presigned URLs)
- Upload progress bar / resumption
- Multipart uploads for >5 GB files (boto3 handles this automatically for `upload_file`; we don't add our own tuning)
- Server-side encryption configuration
- Bucket lifecycle rules
- Access control / IAM policies beyond "use the key the user gave us"
- Mirrored reads (streaming an OME-TIFF directly from R2 into `ViewportEngine`). This needs an `fsspec` integration, which is a bigger cycle.

---

## Architecture

```
Developer runs:

    export CF_R2_ACCOUNT_ID=...
    export CF_R2_ACCESS_KEY_ID=...
    export CF_R2_SECRET_ACCESS_KEY=...
    export CF_R2_BUCKET=squid-demo
    python scripts/upload_acquisition_to_r2.py \
        --path /path/to/acq --prefix 10x_mouse_brain

    -> R2Client.from_env()
    -> client.upload_dir(local_dir=Path('/path/to/acq'), prefix='10x_mouse_brain')
        for each file under local_dir:
            relative = file.relative_to(local_dir)
            client.upload_file(file, key=f"10x_mouse_brain/{relative.as_posix()}")
    -> done; prints summary (N files, total bytes, prefix URL)

Future downstream cycle:

    client = R2Client.from_env()
    url = client.presigned_get_url("10x_mouse_brain/acquisition.yaml", expires_in=3600)
    # Hand url to the browser or to fsspec-backed readers.
```

---

## Components

### 1. `squid_tools/remote/__init__.py`

Empty namespace-marker.

### 2. `squid_tools/remote/r2_client.py`

```python
"""Cloudflare R2 (S3-compatible) client for squid-tools."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator

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
        """Download a key to a local path (creates parents)."""
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
```

### 3. `scripts/upload_acquisition_to_r2.py`

CLI that ties it together:

```python
"""Upload a Squid acquisition directory to Cloudflare R2.

Requires env vars: CF_R2_ACCOUNT_ID, CF_R2_ACCESS_KEY_ID,
CF_R2_SECRET_ACCESS_KEY, CF_R2_BUCKET.

Usage:
    python scripts/upload_acquisition_to_r2.py \
        --path /data/10x_mouse_brain --prefix 10x_mouse_brain
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--prefix", required=True)
    args = parser.parse_args()

    from squid_tools.logger import setup_logging
    from squid_tools.remote.r2_client import R2Client

    setup_logging()
    logger = logging.getLogger("squid_tools.scripts.upload_acquisition_to_r2")
    try:
        client = R2Client.from_env()
    except RuntimeError as e:
        logger.error("%s", e)
        return 2

    if not args.path.is_dir():
        logger.error("--path %s is not a directory", args.path)
        return 2

    keys = client.upload_dir(args.path, args.prefix)
    logger.info("%d files uploaded under prefix %s", len(keys), args.prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## Error Handling

| Failure | Behavior |
|---------|----------|
| Missing env vars | `R2Client.from_env` raises `RuntimeError` listing missing vars |
| Credentials wrong | boto3 raises `ClientError`; caller sees the stack trace |
| `upload_dir` on a file (not a dir) | `ValueError` |
| Network error during upload | boto3 retries; ultimate failure raises |
| `boto3` not installed | Clear `RuntimeError` at `R2Client()` construction |

---

## UX Details

CLI output uses the logger (INFO):
```
[14:22:59] [INFO] [scripts.upload_acquisition_to_r2] uploading /data/10x_mouse_brain...
[14:23:00] [INFO] [remote] uploaded acquisition.yaml -> squid-demo/10x_mouse_brain/acquisition.yaml
[14:23:01] [INFO] [remote] uploaded ome_tiff/0_0.ome.tiff -> squid-demo/10x_mouse_brain/ome_tiff/0_0.ome.tiff
...
[14:24:00] [INFO] [scripts.upload_acquisition_to_r2] 320 files uploaded under prefix 10x_mouse_brain
```

---

## Testing Plan

**(Written at end of all cycles — functional user workflow tests for the complete integrated product. Per-cycle TDD is handled by superpowers during implementation.)**

Placeholder: this cycle's TDD tests live in its implementation plan. The spec's Testing Plan section will be written when all planned cycles are complete, describing end-to-end user workflows to validate the full product.
