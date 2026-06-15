"""Portfolio loading — the single entry point engines use to get holdings.

In ``mock`` mode it reads the packaged sample fixtures (zero credentials). In
``live_readonly`` mode it would call the Schwab adapter (read-only); that path is
wired in app/schwab_client and stays behind config.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import AppConfig
from app.data.contracts import Account, Holding
from app.data.fixtures import load_sample_accounts, load_sample_manual
from app.data.normalize import normalize_accounts, normalize_manual
from app.data.quality import QualityLedger


@dataclass
class Portfolio:
    accounts: list[Account]
    holdings: list[Holding]
    ledger: QualityLedger

    @property
    def schwab_holdings(self) -> list[Holding]:
        return [h for h in self.holdings if h.is_schwab_managed]

    @property
    def manual_holdings(self) -> list[Holding]:
        return [h for h in self.holdings if not h.is_schwab_managed]


def load_portfolio(cfg: AppConfig) -> Portfolio:
    ledger = QualityLedger()
    if cfg.settings.mode == "live_readonly":  # pragma: no cover - requires credentials
        from app.schwab_client.client import SchwabClient  # type: ignore[import-not-found]

        client = SchwabClient.from_config(cfg)
        accounts, schwab = normalize_accounts(client.get_accounts_raw(), cfg, ledger)
    else:
        accounts, schwab = normalize_accounts(load_sample_accounts(), cfg, ledger)
    manual = normalize_manual(load_sample_manual(), cfg, ledger)
    return Portfolio(accounts=accounts, holdings=schwab + manual, ledger=ledger)
