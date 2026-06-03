"""Evaluation: leakage-free faithfulness metrics + external benchmark check."""
from src.eval.metrics import (
    cohens_kappa, evaluate, hallucination_rate, citation_grounding_rate,
    abstention_metrics, directional_faithfulness, inter_mode_kappa,
)
from src.eval.benchmark import benchmark_tier_accuracy, load_truth, normalize_tier

__all__ = [
    "cohens_kappa", "evaluate", "hallucination_rate", "citation_grounding_rate",
    "abstention_metrics", "directional_faithfulness", "inter_mode_kappa",
    "benchmark_tier_accuracy", "load_truth", "normalize_tier",
]
