from __future__ import annotations

import importlib.metadata

from squid_tools.plugins.base import ProcessingPlugin


def discover_plugins() -> dict[str, ProcessingPlugin]:
    plugins: dict[str, ProcessingPlugin] = {}
    eps = importlib.metadata.entry_points()
    squid_eps = (
        eps.select(group="squid_tools.plugins")
        if hasattr(eps, "select")
        else eps.get("squid_tools.plugins", [])
    )
    for ep in squid_eps:
        try:
            plugin_cls = ep.load()
            if isinstance(plugin_cls, type) and issubclass(plugin_cls, ProcessingPlugin):
                instance = plugin_cls()
                plugins[ep.name] = instance
        except Exception:
            continue
    return plugins
