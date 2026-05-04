from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli as stcli


def bundled_path(relative_path: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


if __name__ == "__main__":
    app_path = bundled_path("reservoir_dashboard/app.py")
    sys.argv = [
        "streamlit",
        "run",
        str(app_path),
        "--global.developmentMode=false",
        "--server.headless=true",
    ]
    sys.exit(stcli.main())
