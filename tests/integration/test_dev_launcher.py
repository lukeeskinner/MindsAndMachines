"""Exercise make -> dev.py without starting servers or contacting AWS."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PROBE = '''
import json, os, runpy, sys
from unittest.mock import Mock, patch
keys = ("MODEL_PROVIDER", "AWS_REGION", "BEDROCK_MODEL_ID", "BEDROCK_TIMEOUT_SECONDS")
launched = []
def launch(args, **kwargs):
    if "backend.app.main:app" in args:
        effective_env = kwargs.get("env", os.environ)
        launched.append({key: effective_env.get(key) for key in keys})
    return Mock(pid=1234, returncode=0, poll=lambda: 0, wait=lambda **kw: 0)
with patch("subprocess.Popen", side_effect=launch), patch("os.killpg"):
    runpy.run_path(sys.argv[1], run_name="__main__")
print(json.dumps(launched))
'''


class DevLauncherTests(unittest.TestCase):
    def test_make_dev_preserves_backend_configuration_including_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            probe = Path(temporary) / "probe.py"
            probe.write_text(PROBE)
            for mode in [None, "fake", "bedrock"]:
                with self.subTest(mode=mode):
                    env = {**os.environ, "AWS_REGION": "us-east-1",
                           "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0", "BEDROCK_TIMEOUT_SECONDS": "12"}
                    env.pop("MODEL_PROVIDER", None)
                    # The parent test was launched by make check; don't inherit its
                    # recursive-make flags or command-line variable overrides.
                    for key in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES"):
                        env.pop(key, None)
                    if mode is not None:
                        env["MODEL_PROVIDER"] = mode
                    result = subprocess.run(["make", "--no-print-directory", "-s", "dev",
                                             f"PYTHON={sys.executable} {probe}"],
                                            cwd=ROOT, env=env, text=True, capture_output=True, check=True)
                    self.assertEqual(json.loads(result.stdout.splitlines()[-1]), [{
                        "MODEL_PROVIDER": mode, "AWS_REGION": "us-east-1",
                        "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0", "BEDROCK_TIMEOUT_SECONDS": "12"}])
