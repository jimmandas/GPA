#!/usr/bin/env python3
"""
Diagnostic script to verify SDK availability and functionality.
Run this to debug why evidence_summarizer is returning empty responses.

Usage: python diagnose_sdk.py
"""

import sys
import json
import asyncio


def test_imports():
    """Check if required packages are available."""
    print("=" * 60)
    print("STEP 1: Checking required imports")
    print("=" * 60)

    packages = {
        "claude_agent_sdk": "Claude Agent SDK",
        "jsonschema": "JSON Schema validator",
        "yaml": "YAML parser",
    }

    all_available = True
    for pkg, desc in packages.items():
        try:
            __import__(pkg)
            print(f"✓ {desc} ({pkg})")
        except ImportError:
            print(f"✗ {desc} ({pkg}) — NOT FOUND")
            all_available = False

    print()
    return all_available


def test_agent_import():
    """Try to import the evidence_summarizer agent."""
    print("=" * 60)
    print("STEP 2: Importing Evidence Summarizer agent")
    print("=" * 60)

    try:
        from agents.evidence_summarizer import agent as evidence_summarizer
        print("✓ Evidence Summarizer agent imported successfully")
        print(f"  - Prompt hash: {evidence_summarizer._PROMPT_HASH}")
        print(f"  - Model: {evidence_summarizer._MODEL_SNAPSHOT}")
        return True, evidence_summarizer
    except Exception as e:
        print(f"✗ Failed to import: {e}")
        import traceback
        traceback.print_exc()
        return False, None


async def test_sdk_call(agent_module):
    """Test a minimal SDK call using the agent's internal mechanism."""
    print("\n" + "=" * 60)
    print("STEP 3: Testing SDK call with minimal input")
    print("=" * 60)

    test_submission = {
        "case_id": "test_diagnostic",
        "patient": {"patient_id": "test_pt"},
        "imaging_request": {
            "modality": "CT",
            "body_region": "chest",
            "indication_text": "Test indication"
        },
        "clinical_indication": {
            "diagnosis_code": "C00.0",
            "diagnosis_text": "Test diagnosis"
        },
        "policy_id": "test_policy"
    }

    try:
        result = await agent_module.run(test_submission, "test_diagnostic")
        print(f"✓ SDK call successful")
        print(f"  - Result type: {type(result)}")
        print(f"  - Result keys: {list(result.keys()) if isinstance(result, dict) else 'N/A'}")
        if isinstance(result, dict):
            print(f"  - case_id: {result.get('case_id')}")
            print(f"  - modality: {result.get('modality')}")
        return True
    except Exception as e:
        print(f"✗ SDK call failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all diagnostics."""
    print("\n" + "=" * 60)
    print("SDK & AGENT DIAGNOSTIC")
    print("=" * 60)
    print()

    # Step 1: Check imports
    imports_ok = test_imports()
    if not imports_ok:
        print("\n⚠ DIAGNOSIS: Missing required packages.")
        print("  Install with: pip install jsonschema pyyaml claude-agent-sdk")
        return 1

    # Step 2: Try to import agent
    print()
    agent_ok, agent_module = test_agent_import()
    if not agent_ok:
        print("\n⚠ DIAGNOSIS: Agent import failed (likely prompt hash mismatch).")
        return 1

    # Step 3: Test SDK call
    print()
    sdk_ok = await test_sdk_call(agent_module)

    print("\n" + "=" * 60)
    if sdk_ok:
        print("✓ ALL CHECKS PASSED")
        print("  The SDK is properly configured and responding.")
        print("  You can run: SKIP_INTEGRATION_TESTS=0 python eval/runner.py")
        return 0
    else:
        print("✗ SDK CALL FAILED")
        print("  Possible causes:")
        print("  1. SDK auth/credentials not configured")
        print("  2. Model 'claude-opus-4-1-20250805' not available")
        print("  3. Network/connectivity issue")
        print("  4. SDK exception being raised silently")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
