"""Plugin discovery and registration."""

from __future__ import annotations

from squid_tools.processing.base import ProcessingPlugin


class PluginRegistry:
    """Registry of available processing plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, ProcessingPlugin] = {}

    def register(self, plugin: ProcessingPlugin) -> None:
        """Register a plugin by its name."""
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> ProcessingPlugin | None:
        """Get a plugin by name. Returns None if not found."""
        return self._plugins.get(name)

    def list_names(self) -> list[str]:
        """List all registered plugin names."""
        return list(self._plugins.keys())

    def list_by_category(self, category: str) -> list[ProcessingPlugin]:
        """List plugins matching the given category."""
        return [p for p in self._plugins.values() if p.category == category]

    def list_all(self) -> list[ProcessingPlugin]:
        """List all registered plugins."""
        return list(self._plugins.values())
