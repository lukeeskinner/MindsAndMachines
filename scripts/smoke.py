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
    first = post("turns", {"session_id": session["session_id"],
        "question_id": session["question"]["question_id"], "answer": "a",
        "presentation_preferences": preferences})
    second = post("turns", {"session_id": session["session_id"],
        "question_id": first["next_question"]["question_id"], "answer": "b",
        "presentation_preferences": preferences})
    return session, first, second


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
    session, first, second = run_demo({})
    fixture = json.loads((root / "contracts/fixtures/turn_response.json").read_text(encoding="utf-8"))
    assert {**first, "session_id": "example-session"} == fixture
    focus = next(c for c in second["concepts"] if c["concept_id"] == "admissibility_vs_consistency")
    assert focus == {"concept_id": "admissibility_vs_consistency", "mean": 0.5,
        "interval90": {"lower": 0.1354, "upper": 0.8646}, "evidence_count": 2}
    assert second["assessment"]["outcome"] == "correct" and second["next_question"] is None
    reset = post("sessions", {})
    assert reset["session_id"] != session["session_id"]
    assert reset["concepts"] == session["concepts"] and reset["question"] == session["question"]
    _, formatted_first, formatted_second = run_demo({
        "plain_language": True, "step_by_step": True, "concise": True})
    for original, formatted in [(first, formatted_first), (second, formatted_second)]:
        assert {k:v for k,v in original.items() if k not in {"session_id", "tutor"}} == {
            k:v for k,v in formatted.items() if k not in {"session_id", "tutor"}}
    assert first["tutor"]["text"] != formatted_first["tutor"]["text"]
    assert formatted_first["tutor"]["text"].startswith("1. ")
    print("PASS: actual HTTP golden loop, posterior values, reset, preference isolation.")
finally:
    process.terminate()
    process.wait(timeout=5)
