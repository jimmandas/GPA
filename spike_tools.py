import asyncio
import hashlib
import json

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, tool, create_sdk_mcp_server, AssistantMessage, ToolUseBlock

NUM_RUNS = 5

SYSTEM_PROMPT = """You are a clinical context retriever. Given a case_id and patient_id,
retrieve the patient's imaging history using the patient_history_lookup tool.
Return a JSON summary of the most recent imaging event."""

FIXTURE_CASE = {
    "case_id": "spike_case_tool_001",
    "patient_id": "pt_spike_001"
}

# Deterministic fixture response — same input always returns same output
TOOL_FIXTURE = {
    "pt_spike_001": {
        "patient_id": "pt_spike_001",
        "imaging_history": [
            {
                "date": "2026-02-15",
                "modality": "CT",
                "body_region": "chest",
                "key_finding": "No new nodules; stable post-resection changes"
            }
        ]
    }
}

# Custom tool defined via @tool decorator — in-process MCP server pattern
@tool(
    "patient_history_lookup",
    "Retrieves imaging history for a patient. Returns prior imaging events.",
    {"patient_id": str}
)
async def patient_history_lookup(args):
    """Pure function — same input always returns same output."""
    patient_id = args.get("patient_id", "")
    result = TOOL_FIXTURE.get(patient_id, {"error": "patient not found"})
    return {"content": [{"type": "text", "text": json.dumps(result)}]}

def serialize_event(message) -> dict:
    repr_dict = {"type": type(message).__name__}
    if hasattr(message, "content"):
        repr_dict["content_summary"] = [
            {"type": type(b).__name__, "text": getattr(b, "text", None)}
            for b in (message.content or [])
        ]
    return repr_dict

async def run_once(run_index: int) -> dict:
    # In-process MCP server — custom tool schema registered here
    server = create_sdk_mcp_server(
        name="clinical-tools",
        version="1.0.0",
        tools=[patient_history_lookup]
    )

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        max_turns=3,
        mcp_servers={"clinical-tools": server},
        allowed_tools=["patient_history_lookup"],
        # NOTE: temperature still not configurable via ClaudeAgentOptions — same gap as Day 1.
    )

    events = []
    all_tool_calls = []
    fixture_tool_calls = []  # Only our tools — excludes SDK meta-calls (ToolSearch)
    final_text = ""

    # ClaudeSDKClient required (not query()) when using mcp_servers / custom tools
    async with ClaudeSDKClient(options) as client:
        await client.query(json.dumps(FIXTURE_CASE))
        async for message in client.receive_response():
            event_repr = serialize_event(message)
            events.append(event_repr)

            if isinstance(message, AssistantMessage) and message.content:
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        call = {"tool_name": block.name, "input": block.input}
                        all_tool_calls.append(call)
                        # ToolSearch is an SDK meta-call for deferred schema loading — exclude from fixture hash
                        if block.name != "ToolSearch":
                            fixture_tool_calls.append(call)

            if hasattr(message, "content") and message.content:
                for block in message.content:
                    if hasattr(block, "text"):
                        final_text += block.text

    return {
        "run_index": run_index,
        "final_text_hash": hashlib.sha256(final_text.encode()).hexdigest(),
        "event_count": len(events),
        "all_tool_call_count": len(all_tool_calls),
        "fixture_tool_call_count": len(fixture_tool_calls),
        "event_stream_hash": hashlib.sha256(
            json.dumps(events, sort_keys=True).encode()
        ).hexdigest(),
        "fixture_tool_call_hash": hashlib.sha256(
            json.dumps(fixture_tool_calls, sort_keys=True).encode()
        ).hexdigest(),
        "fixture_tool_calls": fixture_tool_calls,
    }

async def main():
    results = []
    for i in range(NUM_RUNS):
        print(f"Run {i+1}/{NUM_RUNS}...")
        results.append(await run_once(i))

    final_text_hashes = {r["final_text_hash"] for r in results}
    event_stream_hashes = {r["event_stream_hash"] for r in results}
    fixture_tool_call_hashes = {r["fixture_tool_call_hash"] for r in results}
    fixture_tool_call_counts = {r["fixture_tool_call_count"] for r in results}
    all_tool_call_counts = [r["all_tool_call_count"] for r in results]

    print("\n" + "=" * 60)
    print("TOOL-CALL DETERMINISM SPIKE RESULTS")
    print("=" * 60)
    print(f"Runs: {NUM_RUNS}")
    print(f"Unique final-text hashes:         {len(final_text_hashes)} (expect 1)")
    print(f"Unique event-stream hashes:        {len(event_stream_hashes)} (expect 1 — may vary due to ToolSearch metadata)")
    print(f"Unique fixture tool-call hashes:   {len(fixture_tool_call_hashes)} (expect 1 — this is the gate)")
    print(f"Unique fixture tool-call counts:   {len(fixture_tool_call_counts)} (expect 1)")
    print(f"Fixture tool calls per run:        {list(fixture_tool_call_counts)}")
    print(f"All tool calls per run (incl SDK): {all_tool_call_counts}")

    if len(fixture_tool_call_hashes) == 1 and len(fixture_tool_call_counts) == 1:
        print("\n✅ SPIKE PASSES. Fixture tool-call sequence is deterministic.")
        print("   (Event stream may vary due to ToolSearch deferred-schema lookups — SDK internals, not fixture behavior.)")
        print("   Proceed with Context Retriever and Policy Mapper agents.")
        print("   Update ADR-002 with Day 2 result.")
    else:
        print("\n❌ SPIKE FAILS. Non-determinism in fixture tool calls.")
        if len(fixture_tool_call_hashes) > 1:
            print("   Run 1 fixture calls:", json.dumps(results[0]["fixture_tool_calls"], indent=2))
            print("   Run 2 fixture calls:", json.dumps(results[1]["fixture_tool_calls"], indent=2))

if __name__ == "__main__":
    asyncio.run(main())
