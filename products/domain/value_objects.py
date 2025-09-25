from dataclasses import dataclass


@dataclass(frozen=True)
class Vigencia:
    desde: str  # ISO (stub)
    hasta: str | None = None


@dataclass(frozen=True)
class TVPO:
    value: str  # p.ej. "TVPO-25-000123"
