import asyncio
import hashlib
import json

from claude_agent_sdk import query, ClaudeAgentOptions

MODEL_SNAPSHOT = "claude-opus-4-5"
NUM_RUNS = 5

SYSTEM_PROMPT = """You are a clinical evidence extractor. Given a prior auth
submission, return a JSON object with these fields:
- modality (string)
- body_region (string)
- indication_category (one of: initial_diagnosis, staging, post_treatment_surveillance, treatment_response, symptom_workup, other)

Return ONLY valid JSON, no prose."""

FIXTURE_CASE = {
    "case_id": "spike_case_001",
    "imaging_request": {
        "modality": "CT",
        "body_region": "chest",
        "indication_text": "Follow-up of biopsy-proven stage II non-small cell lung cancer, 3 months post-resection, surveillance per NCCN."
    },
    "clinical_indication": {
        "diagnosis_code": "C34.10",
        "diagnosis_text": "Malignant neoplasm of upper lobe, right lung"
    }
}

async def run_once(run_index: int) -> dict:
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        # model omitted — testing with SDK default to isolate model-name error
        max_turns=1,
        allowed_tools=[],
        # NOTE: temperature is NOT configurable in ClaudeAgentOptions.
        # Determinism here is empirical, not architecturally guaranteed.
        # See ADR-002 for implications on Invariant #1 of the Determinism Contract.
    )

    events = []
    final_text = ""

    async for message in query(
        prompt=json.dumps(FIXTURE_CASE),
        options=options
    ):
        event_repr = {"type": type(message).__name__}
        if hasattr(message, "content"):
            event_repr["content_summary"] = [
                {"type": type(b).__name__, "text": getattr(b, "text", None)}
                for b in (message.content or [])
            ]
        events.append(event_repr)

        if hasattr(message, "content") and message.content:
            for block in message.content:
                if hasattr(block, "text"):
                    final_text += block.text

    return {
        "run_index": run_index,
        "final_text": final_text,
        "final_text_hash": hashlib.sha256(final_text.encode()).hexdigest(),
        "event_count": len(events),
        "event_stream_hash": hashlib.sha256(
            json.dumps(events, sort_keys=True).encode()
        ).hexdigest(),
        "events": events,
    }

async def main():
    results = []
    for i in range(NUM_RUNS):
        print(f"Run {i+1}/{NUM_RUNS}...")
        results.append(await run_once(i))

    final_text_hashes = {r["final_text_hash"] for r in results}
    event_stream_hashes = {r["event_stream_hash"] for r in results}
    event_counts = {r["event_count"] for r in results}

    print("\n" + "=" * 60)
    print("DETERMINISM SPIKE RESULTS")
    print("=" * 60)
    print(f"Runs: {NUM_RUNS}")
    print(f"Unique final-text hashes:    {len(final_text_hashes)} (expect 1)")
    print(f"Unique event-stream hashes:  {len(event_stream_hashes)} (expect 1)")
    print(f"Unique event counts:         {len(event_counts)} (expect 1)")

    if len(final_text_hashes) == 1 and len(event_stream_hashes) == 1:
        print("\n✅ SPIKE PASSES — empirically deterministic (temperature not architecturally enforced).")
        print("   Document in ADR-002: temperature gap acknowledged, empirical stability confirmed.")
    else:
        print("\n❌ SPIKE FAILS — non-determinism detected without temperature control.")
        print("   Fallback: standard anthropic SDK. Write ADR-002 documenting failure mode.")
        print("\nRun 1 events:", json.dumps(results[0]["events"], indent=2)[:1000])
        print("\nRun 2 events:", json.dumps(results[1]["events"], indent=2)[:1000])

if __name__ == "__main__":
    asyncio.run(main())
