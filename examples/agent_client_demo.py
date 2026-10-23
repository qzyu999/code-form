"""Demonstrate the API's reasoning loop without calling a model or editing source.

Run from the checkout:
  .venv/Scripts/python.exe examples/agent_client_demo.py --url http://127.0.0.1:7332

An external agent can use the same client and choose its own next actions.
This authored demonstration is not an autonomous model-driven reasoner.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codeform.client import CodeFormClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:7332")
    args = parser.parse_args()
    client = CodeFormClient(args.url)
    job = client.wait(client.analyze("examples/verified-transfer"))
    snapshot = job["snapshot_id"]
    context = client.context(snapshot)
    obligations = context["obligation_set"]["obligations"]
    conservation = next(o for o in obligations if o["property"] == "conservation" and o["name"].endswith("guarded"))
    print(f"Snapshot: {snapshot}")
    print(f"Fixed goal: {conservation['statement']}")
    for strategy in ("simplify", "generated"):
        attempt_job = client.wait(client.submit_attempt(snapshot, conservation, strategy, "API demonstration"))
        result = client.attempt(snapshot, attempt_job["attempt_id"])
        print(f"Strategy {strategy}: {result['status']}")
        if result["status"] == "proved":
            break
    failure = next(o for o in obligations if o["property"] == "nonnegative" and o["name"].endswith("unchecked"))
    attempt_job = client.wait(client.submit_attempt(snapshot, failure, agent="API demonstration"))
    counterexample = client.attempt(snapshot, attempt_job["attempt_id"])
    print(f"Unchecked nonnegative result: {counterexample['status']}")
    if counterexample["status"] == "disproved":
        ref = failure["evidence"][0]
        proposal = client.propose(snapshot, {
            "kind": "repair", "title": "Reject overdrafts before a successful transfer",
            "rationale": "A Lean-checked witness returns a negative balance for source=10, destination=0, amount=11.",
            "content": 'Add `if amount > source: raise ValueError("Insufficient funds")` before returning the balances. '
                       "Add a regression test rejecting (10, 0, 11), then re-analyze and verify against the same nonnegative-output requirement.",
            "obligation_id": failure["id"], "agent": "API demonstration",
            "evidence": [{"path": ref["reference"], "line_start": ref["line_start"], "line_end": ref["line_end"]}],
        })
        print(f"Draft proposal: {proposal['id']} (checked={proposal['checked']}, applied={proposal['applied']})")
    print(f"Context for another agent: {client.base_url}/api/v1/snapshots/{snapshot}/context")


if __name__ == "__main__":
    main()
