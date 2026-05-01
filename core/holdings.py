from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent.parent / "config" / "holdings.yaml"

@dataclass
class HoldingPosition:
    code: str
    name: str
    market: str   # "KR" | "US"
    quantity: int
    avg_price: float
    broker: str = ""

@dataclass
class Holdings:
    positions: list[HoldingPosition]
    cash_krw: float
    cash_usd: float

def load_holdings(path: Path = CONFIG_PATH) -> Holdings:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    positions: list[HoldingPosition] = []
    for item in data.get("positions", []):
        for field in ("code", "name", "market", "quantity", "avg_price"):
            if field not in item:
                raise ValueError(f"holdings.yaml 항목에 필수 필드 누락: {field} ({item})")
        positions.append(HoldingPosition(
            code=str(item["code"]),
            name=item["name"],
            market=item["market"].upper(),
            quantity=int(item["quantity"]),
            avg_price=float(item["avg_price"]),
            broker=item.get("broker", ""),
        ))
    cash = data.get("cash", {})
    return Holdings(
        positions=positions,
        cash_krw=float(cash.get("KRW", 0)),
        cash_usd=float(cash.get("USD", 0)),
    )
