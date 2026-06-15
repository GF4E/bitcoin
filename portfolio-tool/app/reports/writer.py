"""Run-folder writer: reports/runs/YYYY-MM-DD_HHMMSS/ with outputs + metadata.

Report *content* is deterministic (fixed seed, fixed fixtures); only the folder
name carries a timestamp. Tests pass an explicit ``run_id`` for reproducibility.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.config import AppConfig
from app.data.contracts import Assumption, RunMetadata


class RunFolder:
    def __init__(self, cfg: AppConfig, run_id: str | None = None, base: Path | None = None) -> None:
        self.cfg = cfg
        self.started_at = datetime(2026, 6, 15, 16, 0, 0) if run_id else datetime.now()
        self.run_id = run_id or self.started_at.strftime("%Y-%m-%d_%H%M%S")
        root = base or Path(cfg.config_dir).parent / cfg.settings.reports_dir
        self.path = root / self.run_id
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "trade_memos").mkdir(exist_ok=True)

    def write_text(self, name: str, content: str) -> Path:
        p = self.path / name
        p.write_text(content, encoding="utf-8")
        return p

    def write_csv(
        self, name: str, fieldnames: Sequence[str], rows: Sequence[dict[str, Any]]
    ) -> Path:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(fieldnames))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
        return self.write_text(name, buf.getvalue())

    def write_yaml(self, name: str, data: dict[str, Any]) -> Path:
        return self.write_text(name, yaml.safe_dump(data, sort_keys=False))

    def write_assumptions(self, assumptions: Sequence[Assumption]) -> Path:
        data = {
            "assumptions": [
                {
                    "name": a.name,
                    "value": a.value,
                    "label": a.label.value,
                    "load_bearing": a.load_bearing,
                    "rationale": a.rationale,
                }
                for a in assumptions
            ]
        }
        return self.write_yaml("assumptions_used.yaml", data)

    def finalize(self, mode: str, seed: int | None, notes: str = "") -> Path:
        meta = RunMetadata(
            run_id=self.run_id,
            started_at=self.started_at,
            mode=mode,
            compliance_mode=self.cfg.settings.compliance_mode,
            seed=seed,
            config_files=sorted(p.name for p in Path(self.cfg.config_dir).glob("*.yaml")),
            notes=notes,
        )
        return self.write_yaml("run_metadata.yaml", meta.model_dump(mode="json"))
