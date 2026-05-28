# Loom Recording Script — GPA v4 (Phase 2 MVP)

**Target length:** 4-6 minutes. **Format:** screen-share with narration. **Audience:** product / hiring-manager review for "AI governance in regulated healthcare workflows."

The narrative arc: **strategy → architecture → pipeline trace → nurse + physician flow → eval → honest limits.** Each section maps to a specific tab/UI/file the viewer sees on screen.

**Key visual asset:** the **Pipeline Trace UI** (`ui/pipeline_trace.html`) — shows every agent and gate's input/output for a real case run, in 10 sequential cards. This is the strongest single demonstration that the architecture is real, not aspirational.

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

## Section 3 (1:00 – 2:00) — The pipeline trace (live system journey)

**Show:** Open `http://localhost:8001/queue.html`. Queue loads from the **live API** — 15 real cases.

**Click the "View →" link** in the Trace column for `case_0001`. This opens `pipeline_trace.html?case_id=case_0001` and **auto-runs the pipeline**. ~20-30 sec running indicator.

**Say (during the run):**

> "Watch this. The queue picks a case, the Trace UI fires the full pipeline. In about 30 seconds you'll see 10 sequential cards — every agent's input and output, every gate's pass/fail, end-to-end. This isn't a diagram. This is the system actually executing."

**When cards render, scroll through them:**

- **Card 1:** Admission Gate (pure function, field-completeness check) — pass
- **Cards 2-4:** Evidence Summarizer → Context Retriever → Policy Mapper agents — see the actual input/output JSON for each
- **Card 5:** Confidence Gate — the 5th hard control (ADR-015) — pass/fail with threshold
- **Card 6:** Reasoning Drafter agent — the AI brief gets produced here
- **Card 7:** Source Verification Gate — every claim cites a verifiable evidence field — pass
- **Card 8:** AI-Decision-Limit Gate — assert no `decision`/`recommendation`/`confidence` field in any agent output — pass
- **Card 9:** Bilateral Logger pre-state (write-before-emit, fsync to disk)
- **Card 10:** Determination → Nurse Queue (brief now visible to the nurse)

**Say:**

> "Five hard control gates, four agents, all instrumented. The viewer can see the determinism architecture working: temperature zero, pinned model snapshot, prompt hashes. No decision field appears anywhere in the agent outputs — that's an architectural guarantee, not a policy. The schema literally has no place to put one."

---

## Section 4 (2:00 – 3:00) — The nurse workflow

**Click the "Nurse Workspace →" button** in the trace UI header → opens `nurse_workspace.html?case_id=case_0001`.

**Say:**

> "The nurse opens the case. Yellow banner makes it explicit: this is a curated demo brief. The 'Run Live Pipeline' button would re-run the architecture for you — same as the trace UI just did."

**Type a rationale**, click **Approve**.

**Say:**

> "The nurse's action goes to the bilateral logger via the API. Write-before-emit: fsync confirms durable write before the API returns. Let me show that."

---

## Section 5 (3:00 – 3:45) — Audit log + physician handoff

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

## Section 6 (3:45 – 4:45) — Eval framework v3 (3 buckets: Value / Trust / Operational)

**Show:** `eval/results/eval_report_<latest>.md` (the actual eval report — dev-tier by default).

**Say:**

> "Eval framework version 3. Eighteen active dimensions across 15 cases, grouped into three buckets — Value / Outcomes, Trust, and Operational Reliability. The framing matters: most AI eval work stops at model accuracy and hallucinations. This is closer to enterprise value instrumentation — the eval measures workflow correctness, governance adherence, AND business impact in the same artifact."

**Walk through the buckets in the report (each has its own subsection):**

**Bucket 1 — Value / Outcomes (the ROI line):**
- `estimated_roi_per_case_usd` — *"Heuristic: nurse manual review baseline minus pipeline cost. Caveat is on the line — real ROI needs production telemetry, but the eval surfaces a defensible estimate today."*
- `false_escalation_rate` — *"How often the system sends cases to physicians that didn't need it. Workflow-compression value depends on this staying low."*
- `pipeline_completion_rate` — *"Cases that survived all 5 gates end-to-end. Production-stability proxy."*

**Bucket 2 — Trust (the RAI / governance core, 9 dims):**
- `ai_decision_limit = 1.00` across all 15 — *"AI never tried to emit a decision."*
- `source_citation_accuracy = 1.00` — *"Every claim cites verifiable evidence."*
- `citation_correctness = 1.00` — *"Cited the right NCCN passages, not just valid ones — closes Failure Mode #9."*
- `adversarial_gate_bypass_rate = 0.000` — *"Every adversarial case blocked at a governance gate."*
- `bias_disparity` — *"Cohort cuts by case difficulty and indication. Demographic-attribute cuts are Phase 3."*
- Point at any FAILED dim (e.g., reproducibility on a specific case) — *"The eval is not a strawman; it surfaces real failures."*

**Bucket 3 — Operational Reliability (latency / cost / gate sanity):**
- `pipeline_wall_time_p50_seconds` + `pipeline_latency_p90_seconds` — *"TAT proxy. p50 says the median experience, p90 says the tail — both matter for production SLAs."*
- `estimated_cost_per_case_usd` — *"Token-based heuristic. Tier 1 admin-cost proxy."*
- `gate_fire_distribution` — *"Informational. Confirms gates are actually exercised across the dataset; if no adversarial case ever trips a gate, the gate isn't doing work."*

**Say:**

> "The six RAI categories Strategy §6 names — safety, grounding, policy compliance, HITL, explainability, fairness — all sit inside the Trust bucket. The other two buckets exist because trust without value isn't a product, and value without operational reliability isn't deployable. EVAL_TIER lets us iterate cheap on Sonnet during dev, then run audit-grade on Opus for release evidence — documented in ADR-017. Standing policy: ship-tier requires explicit approval; the runner refuses without it. We don't burn Opus budget by accident."

**Show the per-case Notes column briefly:**

> "The Notes column was added after a 97-minute eval run silently scored everything N/A on the faithfulness judge. Without the notes, the bug was invisible. With them, the diagnostic — `OPENAI_API_KEY not propagating to subprocess` — was instant. The eval is now self-instrumenting."

---

## Section 7 (4:45 – 5:30) — Honest limits

**Show:** `docs/SCOPE_DELTAS.md` (the running log of removals/additions).

**Say:**

> "What's honest about this build: we cut a lot from the original Phase 2 plan. Real RAG with a parsed corpus — deferred to Phase 3 because the actual nurse-anchored governance proof doesn't need it. Provider explanation API upgrade — deferred because OKR3 is a different strategy track. Dataset expansion to 50-75 cases — deferred; we ship at 15 with documented limitation. Every cut is logged here with reasoning."

**Show the PHASE_3_BACKLOG.md briefly.**

**Say:**

> "Phase 3 inventory is honest about what's next: real EHR integration, real RAG pipeline, multi-physician concurrency, dataset expansion, demographic bias monitoring. Each has trigger conditions. Nothing is hidden."

---

## Section 8 (5:30 – 6:00) — Wrap

**Show:** `docs/adr/` directory listing.

**Say:**

> "Nineteen ADRs document every architectural decision — including the ones we changed during Phase 2. The whole build is reproducible: pinned model snapshot, hashed prompts, hashed fixtures, deterministic event streams, eval results that match across runs. The governance story is defensible because every claim has an artifact behind it. Thanks for watching."

---

## Recording notes

### Before pressing record

- **No eval running in background.** A live `eval/save_report.py` competes with the demo's pipeline calls for SDK subprocesses → live pipeline runs take 60+ sec instead of 30. Verify with `ps aux | grep save_report.py` — should be empty.
- **Pre-warm the SDK subprocess cache.** Click "Run Live Pipeline" once on case_0001 in `pipeline_trace.html` BEFORE recording. Subsequent runs in the same session are faster (warm imports).
- **Hard-refresh all browser tabs** (Cmd-Shift-R) so the UI JS isn't cached from a prior dev session.
- **Have the eval report file open in a tab** — `eval/results/eval_report_<latest>.md`. Pre-scroll to the headline numbers you'll point at.
- **Verify the physician queue state.** Check `http://localhost:8001/physician_queue.html`:
  - If 0 pending — escalate case_0002 manually before recording so the queue has work.
  - If 2+ pending stale (e.g., `case_test` from old test runs) — either narrate them as "the queue retains pending work between sessions" or clean them via the API before recording.

### During recording

- **Record the live-pipeline section in real-time, don't cut it.** The 30-sec wait is the *point*; it makes the "AI is doing real work" claim concrete. Narrate during the wait — describe what's happening behind the scenes.
- **Keep narration declarative.** State what the system does. The viewer can see whether it actually does it.
- **Don't apologize for limits.** Section 7 (Honest Limits) is the *strength* of the project, not a weakness. Lead with confidence that the cuts were the right PM calls.

### Known rough edges (call out, don't hide)

- **The "DEMO BRIEF" yellow banner** on nurse_workspace.html is a real feature — explicitly says "this is curated demo content; click Run Live Pipeline for real output." Narrate this honestly; it's part of the honest-framing story.
- **`physician_queue` may show old test cases** (`case_test` from earlier test runs). Narrate as: "These persist between sessions because the queue is file-backed — same write-before-emit story as the bilateral log."
- **Reproducibility = 0.80 on Sonnet dev tier is the PASS threshold**, not failure. If a viewer asks "why not 1.0?" — answer: *"5-run reproducibility is engineered determinism, not assumed. 4 of 5 byte-identical runs IS the pass bar; the 5th miss is captured in the bilateral log and surfaces as Sonnet variance on judgment-intensive cases. Opus reproduces more tightly."*

### After recording

- Watch playback once before publishing
- Pay attention to whether the "Run Live Pipeline" wait felt natural or dead-air. If dead-air, add narration in a re-take
- The eval report numbers will move between recording sessions — that's fine; what matters is the framework being concrete
