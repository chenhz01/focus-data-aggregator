# Changelog

## v0.1.1 — 2026-10-12
- Documentation layer completed: README (Problem / How it works / Quickstart / why-not-X with the dated no-equivalent statement / Minimal Fallback / Trade-offs / Limits / FAQ), ALIGNMENT.md 16-item audit, LICENSE (MIT, "zhengming contributors").
- Self-test re-verified green, no code changes needed this round: `python self_test.py` → `SUMMARY: PASS 75/75`.

## v0.1.0 — 2026-10-11
- Initial implementation: record schema validation (date/HH:MM/task/interruptions) with per-record error quarantine, JSONL + JSON-array loading with line-numbered errors, daily and ISO-week aggregation, duration computation with `focus_minutes` fallback, bilingual (EN/中文) keyword interruption classification with declared-category override, focus score `focus/(focus+5×interruptions)`, CLI (`--log`, `--agg day|week`, `--json`, exit 2 on load failure).
- Self-test suite (functional / error / extreme-edge tiers).
