"""Frozen entry point for PyInstaller-built squid-tools.

Sets up Qt plugin paths, environment variables, and crash logging
for the bundled application. Based on ndviewer_light's proven pattern.
"""

import os
import sys
import traceback

_log_path = ""

if getattr(sys, "frozen", False):
    # Running as PyInstaller bundle
    os.environ["QT_PLUGIN_PATH"] = os.path.join(
        sys._MEIPASS, "PySide6", "Qt", "plugins"  # type: ignore[attr-defined]
    )
    _log_path = os.path.join(os.path.dirname(sys.executable), "crash.log")

if "--smoke-test" in sys.argv:
    from installer.smoke_test import run

    run()
else:
    try:
        from squid_tools.__main__ import main

        main()
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        if getattr(sys, "frozen", False) and _log_path:
            with open(_log_path, "w") as f:
                f.write(tb)
            print(f"\nCrash log written to: {_log_path}", file=sys.stderr)
        sys.exit(1)
