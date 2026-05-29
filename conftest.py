"""
Pytest auto-discovers `conftest.py` at the project root and runs it before
any test. This file's job is project-wide test setup that doesn't belong
in individual test files.

What this does:
    - Load .env via python-dotenv so any test that hits a vendor SDK
      (anthropic, openai) finds its auth without depending on shell env.
      Mirrors the load_dotenv() pattern in eval/save_report.py,
      eval/runner.py, api/main.py, diagnose_*.py.

When this matters:
    - SKIP_INTEGRATION_TESTS=1 (the default): most tests skip live SDK
      calls, so env isn't strictly required. This file is a no-op for them.
    - SKIP_INTEGRATION_TESTS=0 (live tests): integration tests hit the
      Claude pipeline and the OpenAI judge. They need env. This file
      ensures it's loaded once for the whole test session.

Notes:
    - Don't put fixtures here unless they're truly project-wide. Sub-folder
      conftest.py files cascade additively.
    - Don't import anything heavy at module top — pytest collects every
      test file via this conftest's chain.
"""

from dotenv import load_dotenv

load_dotenv()
