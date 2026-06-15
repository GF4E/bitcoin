"""Critical correction #4: ARCC appears ONLY in config/examples/arcc_repair_case.yaml.

No engine module may contain ARCC values or branches. This guard scans the app/
source tree and fails on any occurrence.
"""

from __future__ import annotations

from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent.parent / "app"
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


def test_no_arcc_in_app_source() -> None:
    offenders: list[str] = []
    for py in APP_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8").lower()
        if "arcc" in text:
            offenders.append(str(py))
    assert not offenders, f"ARCC leaked into engine code: {offenders}"


def test_arcc_lives_only_in_example_config() -> None:
    hits = [p.name for p in CONFIG_DIR.rglob("*.yaml") if "arcc" in p.read_text("utf-8").lower()]
    assert hits == ["arcc_repair_case.yaml"]
