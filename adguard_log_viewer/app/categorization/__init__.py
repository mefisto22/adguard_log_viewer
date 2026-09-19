"""Rule-driven tagging and categorisation of DNS domains."""

from app.categorization.engine import (
    CategorizationEngine,
    CategoryRule,
    Condition,
    TagRef,
    load_builtin_ruleset,
)

__all__ = [
    "CategorizationEngine",
    "CategoryRule",
    "Condition",
    "TagRef",
    "load_builtin_ruleset",
]
