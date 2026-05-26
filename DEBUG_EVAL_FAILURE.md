# Eval Failure Analysis — 2026-05-26

## Problem
Latest eval run (16:32:53Z) shows both test cases FAILING:
- case_0001: overall_signal_match = 0.00 (expected 1.00)
- case_0002: overall_signal_match = 0.00 (expected 1.00), uncertainty_flag_coverage = 0.00 (expected in [2,3])

## Root Cause
Evidence Summarizer agent returning empty responses (output_hash: null, raw_response_length: 0) in latest runs:
- 2026-05-26T16:32:53.9Z: evidence_summarizer returns empty
- 2026-05-26T16:36:22.3Z: evidence_summarizer returns empty (retry)

Last successful execution: 2026-05-26T04:31:48Z (full pipeline completed)

## Why This Breaks Everything
Pipeline orchestration (pipeline.py:124) calls: `findings = await evidence_summarizer.run(submission, case_id)`

When evidence_summarizer returns empty response, it raises `EvidenceSummarizerError("empty_response", ...)` which:
1. Propagates to pipeline
2. Caught by pipeline exception handler (pipeline.py:184)
3. Returns PipelineResult with status="failed", determination=None
4. Eval runner (runner.py:179) detects determination is None
5. Sets all downstream outputs (reasoning_brief, policy_map, context) to empty dicts
6. Both overall_signal_match and uncertainty_flag_coverage score 0.00

## Environmental Issue
SDK Call Chain:
```
evidence_summarizer.agent.run()
  → _call_evidence_summarizer()
    → query(prompt=user_prompt, options=_AGENT_OPTIONS)
      → Claude SDK returns message stream
      → Accumulates text from all message blocks
    → Returns final_text
  → if not final_text.strip(): raise EvidenceSummarizerError("empty_response")
```

**The SDK is returning an empty stream** (no message blocks with text content).

## Possible Causes
1. **SDK Not Initialized** — claude_agent_sdk not available in execution environment
2. **Credentials/Auth** — SDK initialized but auth failed
3. **Submission Data** — Malformed submission causing SDK to return no response
4. **Model Unavailable** — Specified model (claude-opus-4-1-20250805) not available
5. **Silent Failure** — SDK exception caught and silenced somewhere

## Verification Steps
1. ✗ System Python doesn't have `claude_agent_sdk` or `jsonschema` installed
2. ✗ Cannot import agents directly without these dependencies
3. ✓ Submission files (case_0001.json, case_0002.json) are valid JSON
4. ? Unknown: Where/how the eval was actually run (which Python environment)

## Earlier Successful Run (04:31:48Z)
Shows complete pipeline execution:
- evidence_summarizer: output_hash=sha256:a23ba90e37c334..., raw_response_length=1023
- context_retriever: output_hash=sha256:d1ae617dc205..., completed successfully
- policy_mapper: output_hash=sha256:3e0f081..., completed successfully
- reasoning_drafter: output_hash=sha256:b737e0f..., completed successfully
- pre_state_record: WRITTEN (confirms full pipeline success)

This run had all 4 agents execute successfully with non-empty outputs.

## Next Steps
1. **Verify SDK Environment**: Determine what Python/env is being used to run eval
2. **Check SDK Availability**: Confirm claude_agent_sdk can be imported
3. **Test Agent Import**: Try importing evidence_summarizer to check for hash/config issues
4. **Run Single Case**: Execute pipeline manually for case_0001 with debug output
5. **Inspect SDK Logs**: Check for any SDK-level errors or auth issues
