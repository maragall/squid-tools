"""Upload a Squid acquisition directory to Cloudflare R2.

Requires env vars: CF_R2_ACCOUNT_ID, CF_R2_ACCESS_KEY_ID,
CF_R2_SECRET_ACCESS_KEY, CF_R2_BUCKET.

Usage:
    python scripts/upload_acquisition_to_r2.py \\
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

    logger.info("uploading %s to prefix %s", args.path, args.prefix)
    keys = client.upload_dir(args.path, args.prefix)
    logger.info("%d files uploaded under prefix %s", len(keys), args.prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
