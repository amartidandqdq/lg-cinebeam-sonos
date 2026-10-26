import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def watcher():
    spec = importlib.util.spec_from_file_location("sonos_watcher", ROOT / "watcher" / "sonos-watcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
