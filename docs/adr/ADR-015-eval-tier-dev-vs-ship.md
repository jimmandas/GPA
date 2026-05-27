# ADR-015: Eval Tiers — Dev (Sonnet) vs. Ship (Opus)

**Status:** Accepted
**Date:** 2026-05-27
**Owner:** Jim
**Related:** ADR-009 (eval methodology), ADR-010 (policy_mapper SDK choice)

---

## Context

The eval framework drives a full pipeline run for every case (5 runs × N cases for reproducibility), then scores 8 dimensions. The agent-workflow LLM is the dominant cost: ~160 Claude calls per 8-case eval, ~300 for the scope target of 25-30 cases.

Initial implementation pointed all agents at the production canonical model (`config/model.yaml` → Opus 4.1). That meant every eval iteration during development was a 45+ minute wait — too slow for prompt iteration, schema tweaks, or debugging individual dimensions.

The naive shortcut (swap `model.yaml` to Sonnet for development) violates two constraints:

1. **The model.yaml file is the production audit record.** Changing it for a quick eval taints the production canonical config and creates a window where production behavior could drift if the file isn't reverted.
2. **An eval run on a different model than production doesn't measure production.** Sonnet's reproducibility, adversarial robustness, and rationale faithfulness are all model-dependent. A clean Sonnet eval is not evidence that the Opus production pipeline meets the same bar.

So we need both: fast eval iteration AND audit-grade eval-on-production-model.

---

## Decision

**Eval runs operate in one of two tiers, gated by the `EVAL_TIER` env var.**

```bash
# Default — dev tier (fast iteration)
python eval/save_report.py
# → MODEL_SNAPSHOT_OVERRIDE = "claude-sonnet-4-5-20250929"
# → agents load Sonnet, eval finishes in ~15-25 min

# Ship gate / audit run
EVAL_TIER=ship python eval/save_report.py
# → MODEL_SNAPSHOT_OVERRIDE unset
# → agents fall back to config/model.yaml → Opus 4.1
# → eval finishes in ~45-50 min, results are production-fidelity
```

The mechanism:

- `eval/runner.py` reads `EVAL_TIER` at module-load time.
- If `dev` (or unset): sets `MODEL_SNAPSHOT_OVERRIDE=claude-sonnet-4-5-20250929` BEFORE any agent import.
- If `ship`: leaves the override unset.
- Any other value raises `ValueError` at import — fail loud on typos.

Each agent's `_load_model_snapshot()` checks the env var override first, then falls back to `config/model.yaml`. This same hook lets ops swap models per-run for ad-hoc experiments without editing files.

---

## Why two tiers, not one

| Design | Daily iteration | Audit defense | Cost | Cognitive load |
|---|---|---|---|---|
| Always Opus | Painful (45 min/cycle) | Strong | High | Low |
| Always Sonnet | Fast | **Weak** — eval ≠ prod | Low | Low |
| **Two tiers (this)** | Fast (dev default) | Strong (ship gate) | Low + occasional high | Slightly higher |

The cognitive load — remembering to run `EVAL_TIER=ship` before release — is the main trade-off. It is bounded:

1. The README documents both invocations in the run-the-eval section.
2. The ADR-015 reference is in the eval report header (Phase 2 follow-up).
3. Pre-release checklist names "ran ship-tier eval" as a gate.

A regulator-defensible eval is the deliverable that justifies the ceremony.

---

## What this enables

1. **Calibration eval (future).** Run dev tier and ship tier on the same cases periodically. If dev (Sonnet) signal correlates with ship (Opus) signal, the dev loop is trustworthy. If they diverge, the dev signal is misleading and we need to retire it or recalibrate.

2. **Cheap A/B on model choice.** Want to know if Haiku is good enough as the agent model? Set `MODEL_SNAPSHOT_OVERRIDE` to a Haiku snapshot in a one-off run. The override hook means model swaps don't need code changes.

3. **Cost discipline.** Dev tier on Sonnet is ~80% cheaper per eval than Opus. Encourages the team to iterate frequently rather than batch changes.

---

## Why agents read an env var, not a CLI flag

The model is loaded at agent-module import time, before any function runs. A CLI flag would have to be parsed before the import chain — possible but invasive (would need to refactor the agent module loading). The env var lets the runner.py top-of-file set it once and have every subsequent import respect it.

This also matches ADR-010's pattern for `POLICY_MAPPER_SDK` — env-var-gated runtime choices that don't require code edits.

---

## Consequences

1. **Production behavior unchanged.** `config/model.yaml` stays on Opus. Nothing in the production path reads `MODEL_SNAPSHOT_OVERRIDE` (it's set only by `eval/runner.py`).

2. **Eval reports must record which tier produced them.** A dev-tier report and a ship-tier report are not comparable. Phase 2 follow-up: write the tier into the eval report header so a regulator can see at a glance.

3. **CI runs should default to ship tier on release branches, dev tier on PRs.** Out-of-scope here, but the env-var seam is exactly the place CI gates would hook in.

4. **The model-choice question is now testable.** Before this ADR, the choice between Opus and Sonnet was made once in `model.yaml` and required a full ceremony to revisit. Now ad-hoc experiments are one env var away.

5. **The dev signal can lie.** Documented loudly in the runner docstring and the eval report header. Anyone reading a dev-tier result must know it does not constitute production evidence.

---

## What this ADR does NOT cover

- **Eval-tier metadata in the report.** Dev-tier and ship-tier reports look identical today. They should carry a header `eval_tier: dev | ship` with the model snapshot used. Small follow-up.
- **CI integration.** When ship-tier is required (release branches) vs. dev-tier (PR validation) is a deployment-pipeline decision separate from this ADR.
- **Judge model tier.** The faithfulness judge (GPT-4o) is independent of the agent tier. Pinning that snapshot is its own audit fix (done 2026-05-27).

---

## Related ADRs

- ADR-009 — Eval methodology (now references this for the tier split)
- ADR-010 — Policy mapper SDK choice (precedent for env-var-gated runtime selection)
