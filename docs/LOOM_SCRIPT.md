# Loom Recording Script — GPA v4 (Phase 2 MVP)

**Target length:** 3-5 minutes. **Format:** screen-share with narration. **Audience:** product / hiring-manager review for "AI governance in regulated healthcare workflows."

The narrative arc: **strategy → architecture → flow → eval → honest limits.** Each section maps to a specific tab/UI/file the viewer sees on screen.

---

## Setup (do before recording)

```bash
# 1. Activate venv + load env
source .spike-venv/bin/activate
set -a; source .env; set +a

# 2. Start the API
PYTHONPATH=. uvicorn api.main:app --port 8000 --reload &

# 3. Serve the static UI
python -m http.server 8001 --directory ui &

# 4. Have a few cases in the bilateral log (run the pipeline on 2-3 cases
#    so the audit viewer has something to show — see "Pre-warm" below)
# 5. Have at least one case escalated so the physician queue has work
#    (open nurse_workspace.html?case_id=case_0002, type rationale, click escalate)
```

**Pre-warm shell snippet:**

```bash
for case in case_0001 case_0002 case_0006; do
  curl -s -X POST http://localhost:8000/api/v1/pa/decide \
    -H "Content-Type: application/json" \
    -d @tools/fixtures/submissions/${case}.json > /dev/null
done
```

---

## Section 1 (0:00 – 0:30) — Strategy framing

**Show:** `docs/SCOPE_BASELINE.md` (or briefly the strategy doc title).

**Say:**

> "GPA is a governed prior-authorization review system. The strategy thesis: AI doesn't make the decision. AI compresses the workflow so a nurse can apply judgment faster, with hard runtime controls preventing the AI from substituting for her. Five gates enforce that architecturally — not as policy, not as a monitoring layer."

---

## Section 2 (0:30 – 1:00) — Architecture overview

**Show:** `docs/SCOPE_BASELINE.md` "Determinism Contract" section + a quick scroll through `gates/`.

**Say:**

> "The pipeline runs 4 agents — evidence summarizer, context retriever, policy mapper, reasoning drafter — through 5 gates: admission, source verification, AI-decision-limit, denial, and confidence. The agents have no decision field in their schemas, so the AI architecturally cannot emit a determination. Every claim cites a verifiable evidence field. Every action is logged write-before-emit. Determinism is engineered: temperature zero, pinned model snapshot, prompt SHA-256 hashing."

---

## Section 3 (1:00 – 2:00) — The nurse workflow (live)

**Show:** Open `http://localhost:8001/queue.html` in the browser. The queue loads from the **live API** — viewer sees real cases.

**Click `case_0001`** → opens `nurse_workspace.html?case_id=case_0001`. Yellow "DEMO BRIEF" banner shows — explain it.

**Say:**

> "The nurse opens her queue — these cases are pulled live from the bilateral log via the API. She clicks case_0001 to review. You see the AI brief — supporting evidence, uncertainty flags, nurse focal points. The yellow banner makes it explicit: this is curated demo content. I'll click 'Run Live Pipeline' to show real output."

**Click "Run Live Pipeline" button.** Banner flips to green "LIVE" after 20-60 seconds. Real brief renders.

**Say:**

> "That just ran 4 Claude calls in sequence — evidence summarizer, context retriever, policy mapper, reasoning drafter — through the 5 gates. The brief you're reading is what Opus produced for this case, end-to-end, in about 30 seconds. The schema enforces no decision field anywhere in this output."

**Type a rationale, click Approve.**

**Say:**

> "The nurse's action goes to the bilateral logger with write-before-emit — fsync confirms durable write before the API returns. Let me show that."

---

## Section 4 (2:00 – 2:45) — Audit log + physician handoff

**Open `http://localhost:8001/index.html`** (the audit viewer).

**Say:**

> "This is the live bilateral audit log. Every gate event, every agent output hash, every nurse action — all here. The regulator's question 'who decided this case and why' is one query away."

**Show the nurse_action_record entry for case_0001.**

**Now demo escalation:** Open `nurse_workspace.html?case_id=case_0002`. The judgment-intensive case. Type rationale: "Patient has comorbidities; need physician review of staging documentation." Click **Escalate to Physician**.

**Switch to `physician_queue.html`** — the case is now there.

**Say:**

> "Nurse escalates a judgment-intensive case. The physician queue picks it up immediately — that's the wiring we built into the pipeline. Denial authority sits with the licensed clinician, never the nurse alone, never the AI. The denial gate enforces that architecturally: even in route mode, deny requires a recorded physician ActionRecord with clinical basis and guideline citation."

**Click the case in physician_queue.html.** Show the workspace. Select "Deny", fill in clinical basis + NCCN citation + evidence gaps. Submit.

**Say:**

> "Physician acts. The bilateral logger captures it. The accountability chain is now end-to-end visible: AI assisted, nurse triaged, physician decided, audit log records all three steps."

---

## Section 5 (2:45 – 3:30) — Eval framework

**Show:** `eval/results/eval_report_<latest>.md` (the actual eval report from `EVAL_TIER=dev` or `ship`).

**Say:**

> "The eval scores 11 dimensions across 15 cases. The four per-case dims — source citation accuracy, AI decision limit, rationale faithfulness, decision reproducibility — score every case. The seven aggregate dims include adversarial gate bypass rate (zero tolerance), false escalation rate, confidence calibration, and bias disparity across case cohorts. The faithfulness judge is GPT-4o — different vendor — pinned to a specific snapshot so the verdict is part of the audit record."

**Highlight 1-2 specific numbers from the report.**

**Say:**

> "EVAL_TIER lets the team iterate cheaply on Sonnet during development, then run audit-grade on Opus before release. The dev signal and the ship signal are explicitly different artifacts; both are documented in ADR-017."

---

## Section 6 (3:30 – 4:15) — Honest limits

**Show:** `docs/SCOPE_DELTAS.md` (the running log of removals/additions).

**Say:**

> "What's honest about this build: we cut a lot from the original Phase 2 plan. Real RAG with a parsed corpus — deferred to Phase 3 because the actual nurse-anchored governance proof doesn't need it. Provider explanation API upgrade — deferred because OKR3 is a different strategy track. Dataset expansion to 50-75 cases — deferred; we ship at 15 with documented limitation. Every cut is logged here with reasoning."

**Show the PHASE_3_BACKLOG.md briefly.**

**Say:**

> "Phase 3 inventory is honest about what's next: real EHR integration, real RAG pipeline, multi-physician concurrency, dataset expansion, demographic bias monitoring. Each has trigger conditions. Nothing is hidden."

---

## Section 7 (4:15 – 5:00) — Wrap

**Show:** `docs/adr/` directory listing.

**Say:**

> "Nineteen ADRs document every architectural decision — including the ones we changed during Phase 2. The whole build is reproducible: pinned model snapshot, hashed prompts, hashed fixtures, deterministic event streams, eval results that match across runs. The governance story is defensible because every claim has an artifact behind it. Thanks for watching."

---

## Recording notes

- **Pre-run the "Run Live Pipeline" button once before recording** to warm the SDK subprocess cache; subsequent runs are faster
- **Record the live-pipeline section in real-time, don't cut it** — the 30-sec wait is the *point*; it makes the "AI is doing real work" claim concrete
- **If the physician_queue ends up showing more than one pending case** (because case_0002 was previously escalated in tests), call out the duplicate-pending behavior briefly
- **Keep narration declarative**: state what the system does. The viewer can see whether it actually does it.
- **The eval report numbers will move between recording sessions** — that's fine; what matters is the framework being concrete
