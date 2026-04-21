"""Build a static browser-viewable bundle from a Squid acquisition.

Output folder contents:

    bundle/
    ├── viewer.html          (copied from squid_tools/webdemo/)
    ├── tiles.json           (manifest: bounds + per-tile url + mm coords)
    ├── fov_<n>.png          (one PNG per FOV at the chosen channel/z/t)
    └── …

Open `viewer.html` directly in a browser (file://), or upload the whole
folder to R2 / Cloudflare Pages / any static host.

Usage:
    python scripts/build_browser_bundle.py \\
        --path /path/to/acquisition \\
        --region 0 \\
        --channel 0 \\
        --output bundle/
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--region", default="0")
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument("--z", type=int, default=0)
    parser.add_argument("--timepoint", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--url-prefix",
        default=".",
        help="URL prefix for tile images in tiles.json (use '.' for local, "
             "'https://…' for hosted).",
    )
    args = parser.parse_args()

    from squid_tools.logger import setup_logging
    from squid_tools.viewer.viewport_engine import ViewportEngine

    setup_logging()
    logger = logging.getLogger("squid_tools.scripts.build_browser_bundle")

    if not args.path.is_dir():
        logger.error("--path %s is not a directory", args.path)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)

    engine = ViewportEngine()
    engine.load(args.path, region=args.region)
    bb = engine.bounding_box()
    tile_w_mm, tile_h_mm = engine.tile_size_mm

    manifest: dict = {
        "bounds": {
            "x_min": bb[0], "y_min": bb[1],
            "x_max": bb[2], "y_max": bb[3],
        },
        "channel": args.channel,
        "z": args.z,
        "timepoint": args.timepoint,
        "tiles": [],
    }

    acq = engine._acquisition
    assert acq is not None, "engine.load must have populated the acquisition"
    region_obj = acq.regions[args.region]

    p1, p99 = engine.compute_contrast(channel=args.channel)
    span = max(p99 - p1, 1e-6)

    for fov in region_obj.fovs:
        frame = engine._load_raw(
            fov=fov.fov_index,
            z=args.z,
            channel=args.channel,
            timepoint=args.timepoint,
        )
        normed = np.clip((frame.astype(np.float32) - p1) / span, 0.0, 1.0)
        image = (normed * 255.0).astype(np.uint8)
        out_name = f"fov_{fov.fov_index}.png"
        Image.fromarray(image).save(args.output / out_name, optimize=True)
        manifest["tiles"].append({
            "fov_index": fov.fov_index,
            "x_mm": fov.x_mm,
            "y_mm": fov.y_mm,
            "width_mm": tile_w_mm,
            "height_mm": tile_h_mm,
            "url": f"{args.url_prefix.rstrip('/')}/{out_name}",
        })

    (args.output / "tiles.json").write_text(json.dumps(manifest, indent=2))

    # Copy the viewer page.
    viewer_src = Path(__file__).parent.parent / "squid_tools" / "webdemo" / "viewer.html"
    shutil.copy(viewer_src, args.output / "viewer.html")

    logger.info(
        "bundle built at %s (%d tiles). Open viewer.html to view.",
        args.output, len(manifest["tiles"]),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
