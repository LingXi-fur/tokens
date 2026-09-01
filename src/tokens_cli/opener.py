"""Cross-platform file opening."""
from pathlib import Path
import webbrowser


def open_path(path):
    return webbrowser.open_new_tab(Path(path).resolve().as_uri())
