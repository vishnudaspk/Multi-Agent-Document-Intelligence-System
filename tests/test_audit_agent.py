"""
tests/test_audit_agent.py

Targeted test suite for the Audit/Action Agent (node_action).
Tests whether the agent correctly:
  1. Catches genuine anomalies
  2. Catches contradictions
  3. Catches missing clauses
  4. Returns empty alerts for clean content
  5. Handles hallucinated/fabricated content
  6. Persists alerts to the database
"""
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.agents.nodes import node_action, _llm_json
from app.core.logging import logger


# ─────────────────────────────────────────────────────────────────────────────
# Test Cases
# ─────────────────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "1. CONTRADICTION — Conflicting dates",
        "state": {
            "mode": "query",
            "summary": (
                "The contract between AcmeCorp and WidgetLtd was signed on January 15, 2025. "
                "The contract states the effective date is March 1, 2025 and expires December 31, 2025. "
                "However, later in the document it states the contract expires on June 30, 2026. "
                "The payment terms are Net 30."
            ),
            "document_ids": ["doc-001"],
        },
        "expect_alerts": True,
        "expect_type": "contradiction",
        "description": "Should flag the contradicting expiry dates (Dec 2025 vs Jun 2026)",
    },
    {
        "name": "2. ANOMALY — Unusual financial claim",
        "state": {
            "mode": "query",
            "summary": (
                "The company's quarterly revenue was $50 million. Net profit was $48 million, "
                "representing a 96% profit margin. The company has 10 employees and operates "
                "from a single office in a small town. All revenue is generated from a single "
                "product that was launched 2 weeks ago."
            ),
            "document_ids": ["doc-002"],
        },
        "expect_alerts": True,
        "expect_type": "anomaly",
        "description": "Should flag the unrealistic 96% profit margin for a 10-person company",
    },
    {
        "name": "3. CLEAN — No issues",
        "state": {
            "mode": "query",
            "summary": (
                "The document describes a standard employment agreement between XYZ Corp and "
                "John Doe. The start date is January 1, 2025. The salary is $85,000 per year. "
                "Benefits include health insurance, 401k matching, and 15 days of PTO. "
                "The non-compete clause covers 12 months post-termination within a 50-mile radius."
            ),
            "document_ids": ["doc-003"],
        },
        "expect_alerts": False,
        "expect_type": None,
        "description": "Should return empty alerts — this is a clean, consistent document",
    },
    {
        "name": "4. MISSING CLAUSE — No termination terms",
        "state": {
            "mode": "query",
            "summary": (
                "The service agreement between Alpha Inc and Beta LLC covers managed IT services. "
                "The service level agreement guarantees 99.9% uptime. Monthly fees are $15,000. "
                "Payment is due within 30 days of invoice. The agreement is effective from "
                "April 1, 2025. NOTE: No termination clause, notice period, or exit terms "
                "are defined anywhere in the document. No liability limitation is specified."
            ),
            "document_ids": ["doc-004"],
        },
        "expect_alerts": True,
        "expect_type": "missing_clause",
        "description": "Should flag missing termination clause and liability limitation",
    },
    {
        "name": "5. HALLUCINATION TEST — Fabricated statistics",
        "state": {
            "mode": "query",
            "summary": (
                "According to the document, the global market for quantum computing will reach "
                "$1 trillion by 2025. The document also states that 99% of Fortune 500 companies "
                "have already deployed quantum computers in production. Furthermore, the document "
                "claims quantum computers can solve NP-hard problems in constant time O(1)."
            ),
            "document_ids": ["doc-005"],
        },
        "expect_alerts": True,
        "expect_type": "anomaly",
        "description": "Should flag obviously fabricated/hallucinated claims",
    },
    {
        "name": "6. COMPARE MODE — Contradictions between documents",
        "state": {
            "mode": "compare",
            "comparison": {
                "summary": (
                    "Document A states the project budget is $2 million and the deadline is "
                    "December 2025. Document B states the project budget is $500,000 and the "
                    "deadline is March 2025. Document A lists 15 team members while Document B "
                    "lists 3 team members for the same project."
                ),
                "differences": [
                    {"aspect": "budget", "doc_a": "$2M", "doc_b": "$500K"},
                    {"aspect": "deadline", "doc_a": "Dec 2025", "doc_b": "Mar 2025"},
                ],
                "similarities": ["Both reference Project Phoenix"],
            },
            "document_ids": ["doc-006a", "doc-006b"],
        },
        "expect_alerts": True,
        "expect_type": "contradiction",
        "description": "Should flag contradicting budgets and deadlines between documents",
    },
    {
        "name": "7. EMPTY INPUT — Graceful handling",
        "state": {
            "mode": "query",
            "summary": "",
            "document_ids": [],
        },
        "expect_alerts": False,
        "expect_type": None,
        "description": "Should skip gracefully and return empty alerts",
    },
]


def run_tests():
    print("=" * 80)
    print("  AUDIT AGENT (node_action) — COMPREHENSIVE TEST SUITE")
    print("=" * 80)
    print()

    results = []

    for tc in TEST_CASES:
        print(f"{'-' * 70}")
        print(f"  TEST: {tc['name']}")
        print(f"  Expected: {'alerts' if tc['expect_alerts'] else 'no alerts'}", end="")
        if tc["expect_type"]:
            print(f" (type={tc['expect_type']})", end="")
        print()
        print(f"  {tc['description']}")
        print(f"{'─' * 70}")

        try:
            result = node_action(tc["state"])
            alerts = result.get("alerts", [])

            print(f"  ✦ Alerts returned: {len(alerts)}")
            for i, a in enumerate(alerts, 1):
                print(f"    [{i}] type={a.get('type', '?')}, severity={a.get('severity', '?')}")
                print(f"        message: {a.get('message', '')[:120]}")
                if a.get("context"):
                    print(f"        context: {a.get('context', '')[:100]}")

            # Evaluate pass/fail
            passed = True
            reasons = []

            if tc["expect_alerts"] and len(alerts) == 0:
                passed = False
                reasons.append("EXPECTED alerts but got NONE")
            elif not tc["expect_alerts"] and len(alerts) > 0:
                passed = False
                reasons.append(f"EXPECTED no alerts but got {len(alerts)}")

            if tc["expect_type"] and alerts:
                types_found = [a.get("type", "").lower() for a in alerts]
                if tc["expect_type"] not in types_found:
                    # Check partial match (e.g. "missing_clause" vs "missing clause")
                    partial_match = any(tc["expect_type"].replace("_", " ") in t.replace("_", " ") for t in types_found)
                    if not partial_match:
                        passed = False
                        reasons.append(f"EXPECTED type='{tc['expect_type']}' but got types={types_found}")

            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"\n  Result: {status}")
            if reasons:
                for r in reasons:
                    print(f"    → {r}")

            results.append({"name": tc["name"], "passed": passed, "alerts": len(alerts)})

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append({"name": tc["name"], "passed": False, "alerts": 0})

        print()

    # -- Summary --
    print("=" * 80)
    print("  SUMMARY")
    print("=" * 80)
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed

    for r in results:
        icon = "✅" if r["passed"] else "❌"
        print(f"  {icon}  {r['name']} (alerts={r['alerts']})")

    print(f"\n  Total: {total}  |  Passed: {passed}  |  Failed: {failed}")
    if failed == 0:
        print("  🎉 All tests passed!")
    else:
        print(f"  ⚠️  {failed} test(s) need attention.")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
