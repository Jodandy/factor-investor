"""Every constraint the code upserts against must be declared in the models.

Constraints only defined in migrations get dropped by the next
`alembic revision --autogenerate` (this happened with 3bdf14eb897b, which
broke every build step).
"""

import re
from pathlib import Path

import factor_investor.factors.models
import factor_investor.ingest.models
import factor_investor.pit.models
import factor_investor.universe.models  # noqa: F401  (register all tables)
from factor_investor.ingest.models import Base

SRC = Path(__file__).resolve().parents[2] / "src" / "factor_investor"


def constraint_names_used_in_code() -> set[str]:
    names: set[str] = set()
    for path in SRC.rglob("*.py"):
        text = path.read_text()
        names |= set(re.findall(r'constraint\s*=\s*"([a-z0-9_]+)"', text))
        names |= set(re.findall(r'on_conflict_do_\w+\(\s*"([a-z0-9_]+)"', text))
    return names


def constraint_names_in_models() -> set[str]:
    return {
        c.name
        for table in Base.metadata.tables.values()
        for c in table.constraints
        if c.name
    }


def test_code_finds_constraints_to_check() -> None:
    assert "uq_fundamentals_pit" in constraint_names_used_in_code()


def test_upsert_constraints_are_declared_in_models() -> None:
    missing = constraint_names_used_in_code() - constraint_names_in_models()
    assert not missing, f"Declare in model __table_args__: {sorted(missing)}"
