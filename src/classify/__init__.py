"""Classification: deterministic rule-based (Mode B) + LLM (Mode A) + selection."""
from src.classify.rules import RuleClassifier
from src.classify.select import SelectedVariant, select_for_classification, dedup_key

__all__ = ["RuleClassifier", "SelectedVariant", "select_for_classification", "dedup_key"]
