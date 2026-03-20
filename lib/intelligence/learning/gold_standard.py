"""
MH1 Gold Standard Benchmarking

Curated datasets of known-good outcomes used to validate that model updates
(shadow promotions, drift relearning) don't cause regression.

Firebase path:
  system/intelligence/gold_standards/{dataset_name}

Config:
  config/brain_benchmarks.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    dataset_name: str
    passed: bool
    metrics: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    total_samples: int = 0
    evaluated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "passed": self.passed,
            "metrics": self.metrics,
            "total_samples": self.total_samples,
            "evaluated_at": self.evaluated_at,
        }


class GoldStandardValidator:
    """Validates current model weights against curated benchmark datasets."""

    _DATASET_COLLECTION = "system/intelligence/gold_standards"
    _RESULTS_COLLECTION = "system/intelligence/benchmark_results"

    def __init__(
        self,
        firebase_client: Any,
        config_path: Optional[str] = None,
    ):
        self._firebase = firebase_client
        self._config = self._load_config(config_path)

    def _load_config(self, path: Optional[str] = None) -> Dict[str, Any]:
        """Load benchmark thresholds from config/brain_benchmarks.yaml."""
        if path is None:
            path = str(
                Path(__file__).resolve().parent.parent.parent.parent
                / "config"
                / "brain_benchmarks.yaml"
            )
        try:
            import yaml
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def validate(
        self,
        dataset_name: Optional[str] = None,
    ) -> List[BenchmarkResult]:
        """Run validation against one or all gold standard datasets."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        standards = self._config.get("gold_standards", {})

        if dataset_name:
            standards = {k: v for k, v in standards.items() if k == dataset_name}

        results: List[BenchmarkResult] = []

        for name, spec in standards.items():
            dataset = self._load_dataset(name)
            if not dataset:
                logger.info(f"Gold standard dataset '{name}' has no data yet, skipping")
                continue

            min_samples = spec.get("min_samples", 30)
            if len(dataset) < min_samples:
                logger.info(
                    f"Dataset '{name}' has {len(dataset)}/{min_samples} samples, skipping"
                )
                continue

            br = BenchmarkResult(
                dataset_name=name,
                passed=True,
                total_samples=len(dataset),
                evaluated_at=now,
            )

            for metric_name, metric_spec in spec.get("metrics", {}).items():
                threshold = metric_spec.get("threshold", 1.0)
                computed = self._compute_metric(metric_name, dataset)
                passed = self._check_threshold(metric_name, computed, threshold)

                br.metrics[metric_name] = {
                    "value": computed,
                    "threshold": threshold,
                    "passed": passed,
                    "description": metric_spec.get("description", ""),
                }
                if not passed:
                    br.passed = False

            results.append(br)
            self._persist_result(br)

            status = "PASS" if br.passed else "FAIL"
            logger.info(f"Benchmark '{name}': {status} ({br.total_samples} samples)")

        return results

    def _load_dataset(self, name: str) -> List[Dict[str, Any]]:
        """Load gold standard data from Firebase."""
        if not self._firebase or not hasattr(self._firebase, "get_document"):
            return []
        try:
            doc = self._firebase.get_document(self._DATASET_COLLECTION, name)
            if doc:
                return doc.get("samples", [])
        except Exception as e:
            logger.debug(f"Could not load dataset '{name}': {e}")
        return []

    def _compute_metric(
        self, metric_name: str, dataset: List[Dict[str, Any]]
    ) -> float:
        """Compute a metric value from the dataset."""
        if metric_name == "prediction_error":
            errors = [
                abs(s.get("prediction_error", 0)) for s in dataset if "prediction_error" in s
            ]
            return sum(errors) / len(errors) if errors else 0.0

        if metric_name == "success_rate":
            successes = [s.get("goal_completed", False) for s in dataset]
            return sum(successes) / len(successes) if successes else 0.0

        if metric_name == "segment_accuracy":
            correct = sum(
                1 for s in dataset
                if s.get("predicted_segment") == s.get("actual_segment")
            )
            return correct / len(dataset) if dataset else 0.0

        logger.debug(f"Unknown metric '{metric_name}', returning 0.0")
        return 0.0

    def _check_threshold(
        self, metric_name: str, value: float, threshold: float
    ) -> bool:
        """Check if a metric passes its threshold.

        For error metrics (lower is better), value must be <= threshold.
        For rate/accuracy metrics (higher is better), value must be >= threshold.
        """
        error_metrics = {"prediction_error", "mean_absolute_error"}
        if metric_name in error_metrics:
            return value <= threshold
        return value >= threshold

    def _persist_result(self, result: BenchmarkResult):
        if not self._firebase or not hasattr(self._firebase, "set_document"):
            return
        try:
            doc_id = f"{result.dataset_name}_{result.evaluated_at[:10]}"
            self._firebase.set_document(
                self._RESULTS_COLLECTION, doc_id, result.to_dict(), merge=True,
            )
        except Exception as e:
            logger.debug(f"Failed to persist benchmark result: {e}")


__all__ = ["BenchmarkResult", "GoldStandardValidator"]
