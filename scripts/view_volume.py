"""Minimal 3D volume viewer script.

Usage:
    python scripts/view_volume.py <acquisition_path> \
        [--region REGION] [--fov FOV] [--channel CHANNEL]

Opens a Qt window showing a 3D ray-marched view of a single FOV's
z-stack. Drag to rotate, scroll to zoom.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Squid acquisition directory")
    parser.add_argument("--region", default="0", help="Region id (default: 0)")
    parser.add_argument("--fov", type=int, default=0, help="FOV index")
    parser.add_argument(
        "--channel",
        type=int,
        default=None,
        help="Single channel for grayscale view (omit for multi-channel)",
    )
    parser.add_argument("--timepoint", type=int, default=0)
    parser.add_argument("--level", type=int, default=0, help="Pyramid level")
    parser.add_argument(
        "--cmap",
        default="grays",
        help="Colormap for single-channel mode (grays, viridis, hot, ...)",
    )
    args = parser.parse_args()

    from squid_tools.logger import setup_logging
    setup_logging()

    from squid_tools.viewer.viewport_engine import ViewportEngine
    from squid_tools.viewer.volume_canvas import Volume3DCanvas

    app = QApplication(sys.argv)

    engine = ViewportEngine()
    engine.load(args.path, region=args.region)

    canvas = Volume3DCanvas(size=(800, 800))

    if args.channel is not None:
        vol = engine.get_volume(
            fov=args.fov,
            channel=args.channel,
            timepoint=args.timepoint,
            level=args.level,
        )
        canvas.set_volume(
            vol,
            voxel_size_um=engine.voxel_size_um(),
            cmap=args.cmap,
        )
    else:
        nc = len(engine._acquisition.channels)
        vols = [
            engine.get_volume(
                fov=args.fov, channel=c,
                timepoint=args.timepoint, level=args.level,
            )
            for c in range(nc)
        ]
        clims = [(float(v.min()), float(v.max())) for v in vols]
        cmaps = ["reds", "greens", "blues", "hot", "viridis", "plasma"][:nc]
        canvas.set_channel_volumes(
            vols, clims, cmaps,
            voxel_size_um=engine.voxel_size_um(),
        )

    native = canvas.native_widget()
    native.setWindowTitle(
        f"Volume3D — FOV {args.fov}"
        + (f" ch {args.channel}" if args.channel is not None else " (all channels)"),
    )
    native.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
