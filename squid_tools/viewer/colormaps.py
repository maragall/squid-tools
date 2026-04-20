"""Cephla channel colormap mapping.

Maps channel names (from Squid filename conventions) to vispy colormaps
and hex colors. Pattern from Cephla-Lab/image-stitcher.
"""

from __future__ import annotations

# Hex colors for UI display (borders, labels, legends)
CHANNEL_COLORS: dict[str, str] = {
    "405": "#0000FF",   # Blue (DAPI)
    "488": "#00FF00",   # Green (GFP)
    "561": "#FFCF00",   # Yellow (RFP/mCherry)
    "638": "#FF0000",   # Red (Cy5)
    "730": "#770000",   # Dark red (Cy7)
    "_B": "#0000FF",
    "_G": "#00FF00",
    "_R": "#FF0000",
}

# Vispy colormap names
# Vispy colormap names (must be valid vispy.color.colormap names)
# Valid: 'grays', 'blues', 'greens', 'reds', 'viridis', 'plasma', 'inferno',
#        'magma', 'autumn', 'cool', 'hot', 'ice', 'spring', 'summer', 'winter'
_CHANNEL_CMAPS: dict[str, str] = {
    "405": "blues",
    "488": "greens",
    "561": "autumn",
    "638": "reds",
    "730": "reds",
    "_B": "blues",
    "_G": "greens",
    "_R": "reds",
}


def get_channel_colormap(channel_name: str) -> str:
    """Return vispy colormap name for a channel. Falls back to 'grays'."""
    for pattern, cmap in _CHANNEL_CMAPS.items():
        if pattern in channel_name:
            return cmap
    return "grays"


def get_channel_hex(channel_name: str) -> str:
    """Return hex color for a channel. Falls back to white."""
    for pattern, color in CHANNEL_COLORS.items():
        if pattern in channel_name:
            return color
    return "#FFFFFF"


# RGB float tuples for additive compositing
_CHANNEL_RGB: dict[str, tuple[float, float, float]] = {
    "405": (0.0, 0.0, 1.0),   # Blue
    "488": (0.0, 1.0, 0.0),   # Green
    "561": (1.0, 0.81, 0.0),  # Yellow
    "638": (1.0, 0.0, 0.0),   # Red
    "730": (0.47, 0.0, 0.0),  # Dark red
    "_B": (0.0, 0.0, 1.0),
    "_G": (0.0, 1.0, 0.0),
    "_R": (1.0, 0.0, 0.0),
}


def get_channel_rgb(channel_name: str) -> tuple[float, float, float]:
    """Return RGB float tuple for a channel. Falls back to white."""
    for pattern, rgb in _CHANNEL_RGB.items():
        if pattern in channel_name:
            return rgb
    return (1.0, 1.0, 1.0)

