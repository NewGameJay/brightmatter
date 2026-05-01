"""Analysis engine — orchestrates both detection layers.

Layer 1: Deterministic detectors (fast, always-on)
Layer 2: LLM agents (nuanced, triggered by signals or on-demand)
"""

from __future__ import annotations

import logging
from typing import Any

from brightmatter.analysis.agents import AgentRunner
from brightmatter.analysis.detectors import run_all_detectors
from brightmatter.models.patterns import Pattern, Signal
from brightmatter.patterns.episodes import EpisodeTracker
from brightmatter.patterns.recorder import PatternRecorder
from brightmatter.storage.database import Database
from brightmatter.storage.repository import Repository

logger = logging.getLogger("brightmatter.analysis")


class AnalysisEngine:
    """Runs the full analysis pipeline: detect → record → diagnose → learn."""

    def __init__(self, db: Database, repo: Repository):
        self.db = db
        self.repo = repo
        self.recorder = PatternRecorder(repo)
        self.episode_tracker = EpisodeTracker(repo, db)
        self.agent_runner = AgentRunner()

    def run_full_analysis(self, use_agents: bool = True) -> dict[str, Any]:
        """Run the complete analysis pipeline."""
        results: dict[str, Any] = {}

        # Layer 1: Deterministic detection
        logger.info("Running deterministic detectors...")
        signals = run_all_detectors(self.db)
        results["signals"] = len(signals)
        logger.info("Found %d signals from detectors", len(signals))

        # Record signals
        for s in signals:
            self.repo.insert_signal(s)

        # Group signals into patterns
        patterns = self.recorder.record_from_signals(signals)
        results["patterns"] = len(patterns)
        logger.info("Recorded %d patterns from signals", len(patterns))

        # Process pending episodes
        episodes = self.episode_tracker.process_pending_episodes()
        results["episodes"] = len(episodes)
        logger.info("Processed %d episodes", len(episodes))

        # Layer 2: LLM agents (if available and requested)
        if use_agents and self.agent_runner.is_available:
            results["agent_analysis"] = self._run_agents(signals, patterns)
        elif use_agents:
            logger.info("LLM agents unavailable (no ANTHROPIC_API_KEY) — skipping Layer 2")
            results["agent_analysis"] = None

        return results

    def run_detectors_only(self) -> list[Signal]:
        """Run only Layer 1 detectors — fast, no LLM calls."""
        signals = run_all_detectors(self.db)
        for s in signals:
            self.repo.insert_signal(s)
        self.recorder.record_from_signals(signals)
        return signals

    def audit_account(self, account_id: str) -> dict[str, Any]:
        """Run the Account Auditor agent on a single account."""
        if not self.agent_runner.is_available:
            return {"error": "ANTHROPIC_API_KEY not configured"}

        account = self.repo.get_account(account_id)
        if not account:
            return {"error": f"Account {account_id} not found"}

        summary = self.repo.account_summary(account_id, days=30)
        signals_data = self.repo.get_signals(account_id=account_id)

        account_data = {
            "account": account.model_dump(mode="json"),
            "performance_30d": summary,
        }
        signal_list = []
        if signals_data and signals_data.get("signal_id"):
            for i in range(len(signals_data["signal_id"])):
                signal_list.append({k: v[i] for k, v in signals_data.items()})

        result = self.agent_runner.audit_account(account_data, signal_list)
        return result.model_dump()

    def spot_cross_account_patterns(self) -> dict[str, Any]:
        """Run the Pattern Spotter agent across all accounts."""
        if not self.agent_runner.is_available:
            return {"error": "ANTHROPIC_API_KEY not configured"}

        accounts = self.repo.list_accounts()
        cross_data = self.repo.cross_account_metrics(days=30)

        account_profiles = []
        for a in accounts:
            profile = a.model_dump(mode="json")
            profile["summary_30d"] = self.repo.account_summary(a.account_id, days=30)
            account_profiles.append(profile)

        data = {
            "accounts": account_profiles,
            "aggregate_metrics": cross_data,
        }
        result = self.agent_runner.spot_patterns(data)
        return result.model_dump()

    def _run_agents(self, signals: list[Signal], patterns: list[Pattern]) -> dict[str, Any]:
        """Run LLM agents on critical signals."""
        critical_signals = [s for s in signals if s.severity.value == "critical"]

        if not critical_signals:
            logger.info("No critical signals — skipping LLM diagnosis")
            return {"diagnoses": 0}

        diagnoses = []
        accounts_to_diagnose = {s.account_id for s in critical_signals}

        for account_id in list(accounts_to_diagnose)[:5]:
            account_signals = [s for s in critical_signals if s.account_id == account_id]
            signal_data = {"signals": [s.model_dump(mode="json") for s in account_signals]}

            account = self.repo.get_account(account_id)
            context = {
                "account": account.model_dump(mode="json") if account else {},
                "performance_30d": self.repo.account_summary(account_id, days=30),
            }

            try:
                diagnosis = self.agent_runner.interpret_signals(signal_data, context)
                diagnoses.append(diagnosis.model_dump())
                logger.info("Diagnosed %s: %s (confidence: %.0f%%)",
                            account_id, diagnosis.root_cause, diagnosis.confidence * 100)
            except Exception:
                logger.exception("Failed to diagnose signals for %s", account_id)

        return {"diagnoses": len(diagnoses), "results": diagnoses}
