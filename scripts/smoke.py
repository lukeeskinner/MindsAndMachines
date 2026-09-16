"""Exercise the actual local HTTP server; no browser/API mocking or cloud calls."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

root = Path(__file__).resolve().parent.parent
os.chdir(root)
with socket.socket() as probe:
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
base = f"http://127.0.0.1:{port}"


def post(path, body):
    request = Request(base + "/api/v1/" + path, data=json.dumps(body).encode(),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def run_demo(preferences):
    session = post("sessions", {})
    question = session["question"]
    results = []
    for expected_id, answer in [("relationship-q01", "a"), ("relationship-q04", "a"),
                                ("relationship-q03", "a"), ("relationship-q02", "b")]:
        assert question["question_id"] == expected_id
        result = post("turns", {"session_id": session["session_id"],
            "question_id": question["question_id"], "answer": answer,
            "presentation_preferences": preferences})
        results.append(result)
        question = result["next_question"]
    assert question is None
    return session, results


process = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.app.main:app",
    "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
    env={**os.environ, "MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": "",
         "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": ""})
try:
    for _ in range(50):
        try:
            post("sessions", {})
            break
        except (URLError, ConnectionError):
            if process.poll() is not None:
                raise RuntimeError("Smoke server exited before startup")
            time.sleep(0.1)
    else:
        raise RuntimeError("Smoke server did not start")
    session, results = run_demo({})
    first, second, third, final = results
    fixture = json.loads((root / "contracts/fixtures/turn_response.json").read_text(encoding="utf-8"))
    # The original evidence/diagnosis is unchanged; the expanded catalog changes
    # the selected teaching and follow-up, not the shared response contract.
    assert {k: first[k] for k in ("assessment", "concepts", "trace", "mode", "provider")} == {
        k: fixture[k] for k in ("assessment", "concepts", "trace", "mode", "provider")}
    assert [r["decision"]["kind"] for r in results if r["decision"]] == [
        "socratic_hint", "diagnostic_probe", "worked_example"]
    focus = next(c for c in second["concepts"] if c["concept_id"] == "admissibility_vs_consistency")
    assert focus == {"concept_id": "admissibility_vs_consistency", "mean": 0.5,
        "interval90": {"lower": 0.1354, "upper": 0.8646}, "evidence_count": 2}
    assert second["assessment"]["outcome"] == "correct"
    assert final["decision"] is None and final["next_question"] is None
    final_focus = next(c for c in final["concepts"] if c["concept_id"] == "admissibility_vs_consistency")
    assert final_focus["evidence_count"] == 4 and final_focus["mean"] == 4 / 6
    reset = post("sessions", {})
    assert reset["session_id"] != session["session_id"]
    assert reset["concepts"] == session["concepts"] and reset["question"] == session["question"]
    _, formatted_results = run_demo({
        "plain_language": True, "step_by_step": True, "concise": True})
    for original, formatted in zip(results, formatted_results):
        assert {k:v for k,v in original.items() if k not in {"session_id", "tutor"}} == {
            k:v for k,v in formatted.items() if k not in {"session_id", "tutor"}}
        if original["decision"]:
            assert original["tutor"]["text"] != formatted["tutor"]["text"]
            assert formatted["tutor"]["text"].startswith("1. ")
    print("PASS: actual HTTP expanded loop, all three interventions, fresh questions, posterior values, reset, preference isolation.")
finally:
    process.terminate()
    process.wait(timeout=5)
