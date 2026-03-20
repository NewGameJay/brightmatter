"""
Fireflies.ai Meeting Intelligence — Ingestion Pipeline

Fetches meeting transcripts from Fireflies.ai, classifies them,
extracts structured insights, detects cross-call patterns,
and stores everything in Firebase for the intelligence system.

Components:
    client.py      — GraphQL API client
    classifier.py  — Meeting type classification + client attribution
    extractor.py   — LLM-powered insight extraction + cross-call connections
    store.py       — Firebase storage (transcripts, insights, connections)
    ingest.py      — Orchestrator (fetch → classify → extract → store → connect)
    config.py      — Configuration, filters, and constants
"""
