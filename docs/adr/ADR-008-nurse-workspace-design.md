# ADR-008: Nurse Workspace UI Design

**Status:** Accepted
**Date:** 2026-05-25
**Owner:** Jim

---

## Context

In the AI-Assists / Human-Decides design (ADR-000), the nurse is the central actor. Every architectural choice exists to serve her judgment while preventing the system from substituting for it. That principle constrains the UI.

The wrong UI for this design is "AI says approve, click here to accept." That collapses the nurse into a rubber stamp and defeats the purpose of the AI-Assists framing.

The right UI surfaces AI-extracted evidence and structured reasoning in a format that supports — not replaces — the nurse's clinical judgment.

---

## Decision

**Three UI surfaces, each with a specific role:**

| File | Role | Primary user |
|---|---|---|
| `ui/queue.html` | Case queue — list of cases awaiting review, with metadata | Nurse (entry point) |
| `ui/nurse_workspace.html` | Per-case review — AI brief + action buttons | Nurse (decision-making) |
| `ui/index.html` | Audit log viewer — case-by-case decision trail with hashes | Governance reviewer / auditor |

The Nurse Workspace is the surface that matters most for the AI-Assists framing. Its specific design choices:

### 1. The brief is labeled AI-generated

A prominent header reads: *"AI-Surfaced Evidence — for your review"*. No ambiguity about who produced the content.

### 2. The brief is structured, not free text

Four sections, mirroring the `reasoning_brief.json` schema:
- **Supporting Evidence** — claims that argue for approval, each with a `source_ref` link the nurse can click to verify
- **Uncertainty Flags** — issues the AI surfaced as ambiguous
- **Nurse Focal Points** — 2–3 specific things the AI thinks deserve human attention
- **AI Rationale** — short narrative summary

This structure forces the AI to organize its output into auditable parts. It also gives the nurse a consistent layout to learn — she always knows where to find what.

### 3. No "Approve" button is enabled until the nurse types a rationale

The decision action buttons (Approve, Escalate-to-Physician, Pend) are disabled until the nurse has typed text into a required `rationale` field. This is enforced both in the UI (button disabled) and at the API layer (`record_nurse_decision` rejects empty/whitespace rationale).

This is the architectural answer to "did the nurse actually read the brief or just click through?" — every decision has an explicit nurse-written rationale tied to it in the audit log.

### 4. No "AI recommends" indicator

The UI does not display anything like "AI suggests: Approve" or "AI confidence: 0.87". Two reasons:

- The AI cannot emit a decision (ADR-007) and does not emit confidence — there is nothing to display.
- Even if such a value existed, displaying it would anchor the nurse to the AI's framing and undermine independent judgment.

### 5. Every claim has a "show source" link

Each item in Supporting Evidence and Uncertainty Flags shows its `source_ref` and lets the nurse drill into the underlying field (submission text, prior imaging finding, etc.). The auditability of the reasoning brief is exposed to the nurse, not just to the audit log.

---

## Why HTML Static Files, Not React / Next.js

The MVP UI is three static HTML files plus a small `app.js`. Reasons:

- **Demo surface clarity:** A static HTML file is something anyone can open and inspect. A bundled SPA hides what's actually shown.
- **No build step in demos:** Recording a 3-minute Loom is easier when there's no `npm run dev` to wrangle.
- **No state that lives in the browser:** All state is in the bilateral log + API. The UI is a thin render.
- **Phase 2 swap room:** The Nurse Queue + Workspace pattern transplants to React / Next.js trivially when the demo surface needs to become a real frontend.

---

## What This UI Doesn't Do (Honest Limits)

- **No authentication / authorization.** Anyone with the URL can act as the nurse.
- **No real-time updates.** Queue refreshes on page reload.
- **No assignment / multi-nurse coordination.** One queue, no claim/release semantics.
- **No mobile optimization.** Desktop-first layout.

All four are appropriate Phase 2 / production concerns. None of them affect the governance proof the MVP is producing.

---

## Consequences

1. **The brief is read by a human as a structured document, not by a downstream system as machine-parseable JSON.** This forces the AI's output to be useful to a clinician, not just structurally valid.
2. **Every nurse decision is paired with a typed rationale.** No silent clickthroughs. This is the substrate for the v2 multi-rater agreement metric (Cohen's κ — two nurses' rationales can be qualitatively compared even before numeric agreement is measured).
3. **The audit log viewer (`ui/index.html`) is separate from the nurse workspace.** A governance reviewer auditing a case sees a different view than the nurse who decided it. Both views derive from the same `decision_log/{case_id}.jsonl`.
4. **The forbidden "AI confidence" / "AI recommendation" displays don't exist** — because the underlying fields don't exist (ADR-007). The UI's restraint is structurally enforced, not policy-enforced.

---

## Related ADRs

- ADR-000 — Solution shape that requires this UI restraint
- ADR-007 — AI-Decision-Limit Gate (the architectural omission that makes "no AI recommends" trivial — there's no field to display)
- ADR-005 — Write-before-emit (the audit log this UI reads from)
