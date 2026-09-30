"""End-to-end self-check on a throwaway target. Run: python3 -m unittest discover tests"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HARNESS = Path(__file__).resolve().parent.parent / "harness.py"


def run(*args):
    return subprocess.run([sys.executable, str(HARNESS), *args], capture_output=True, text=True)


class HarnessTest(unittest.TestCase):
    def test_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, asm = Path(tmp, "target"), Path(tmp, "asm")
            (target / "src dir").mkdir(parents=True)
            (target / "src dir" / "app.py").write_text("a = 1\nsecret = 'x'\nb = 2\n")
            (target / ".hidden").write_text("h")

            ok = lambda *a: self.assertEqual(run(*a).returncode, 0, run(*a).stdout + run(*a).stderr)
            bad = lambda msg, *a: self.assertNotEqual(run(*a).returncode, 0, msg)

            ok("baseline", str(asm), "--target", str(target), "--project", "T")
            bad("baseline must be immutable", "baseline", str(asm), "--target", str(target), "--project", "T")
            bad("must refuse to write inside target", "baseline", str(target / "a"), "--target", str(target), "--project", "T")
            ok("verify", str(asm))

            ev = json.loads(run("evidence", str(asm), "src dir/app.py", "2").stdout)
            self.assertEqual(ev["excerpt"], "secret = 'x'")
            bad("path traversal", "evidence", str(asm), "../etc/passwd", "1")

            for d in ("findings", "controls", "runtime"):
                (asm / d).mkdir()
            f = asm / "findings" / "F-BSEC-001.json"
            hyp = {"id": "F-BSEC-001", "title": "t | x", "severity": "high", "category": "security",
                   "status": "hypothesis", "author": "backend-security-review", "description": "d",
                   "evidence": [ev]}
            f.write_text(json.dumps(hyp))
            ok("check", str(asm))

            validation = {"by": "finding-validator", "outcome": "KEEP", "disproof_attempts": "no guard upstream",
                          "ponytail": "minimal fix"}
            confirmed = {**hyp, "status": "confirmed", "validation": validation, "evidence_level": 4,
                         "call_path": "route -> app.py:2", "controls_checked": "none", "impact": "leak"}

            def rejects(msg, rec, path=f):
                path.write_text(json.dumps(rec))
                bad(msg, "check", str(asm))

            rejects("confirmed without validator", {**hyp, "status": "confirmed"})
            rejects("validator cannot validate own record", {**confirmed, "author": "finding-validator"})
            rejects("outcome must match status", {**confirmed, "validation": {**validation, "outcome": "REJECT"}})
            rejects("high needs level 4", {**confirmed, "evidence_level": 2})
            rejects("confirmed needs call path", {**confirmed, "call_path": ""})
            rejects("fabricated excerpt", {**hyp, "evidence": [{**ev, "excerpt": "made up"}]})
            rejects("runtime item must exist", {**confirmed, "status": "runtime_validation",
                                                "validation": {**validation, "outcome": "RUNTIME_VALIDATION"},
                                                "runtime_item": "RV-BSEC-001"})
            rejects("id pattern", {**hyp, "id": "bad"}, asm / "findings" / "bad.json")
            (asm / "findings" / "bad.json").unlink()

            f.write_text(json.dumps(confirmed))
            (asm / "controls" / "C-BSEC-001.json").write_text(json.dumps(
                {"id": "C-BSEC-001", "title": "guard", "author": "backend-security-review",
                 "description": "works", "evidence": [ev]}))
            (asm / "runtime" / "RV-BSEC-001.json").write_text(json.dumps(
                {"id": "RV-BSEC-001", "question": "RLS on?", "why": "tenant isolation",
                 "how_to_verify": "query pg_policies", "author": "backend-security-review", "status": "open"}))
            ok("check", str(asm))
            report = run("report", str(asm)).stdout
            for s in ("### F-BSEC-001: t | x", "t \\| x", "C-BSEC-001", "RV-BSEC-001"):
                self.assertIn(s, report)
            out = asm / "reports" / "r.md"
            ok("report", str(asm), "-o", str(out))
            self.assertEqual(out.read_text(), report, "report must be reproducible")
            bad("reports are never overwritten", "report", str(asm), "-o", str(out))

            (target / "src dir" / "app.py").write_text("changed\n")
            (target / "new.txt").write_text("n")
            (target / ".hidden").unlink()
            (target / "link").symlink_to("new.txt")
            res = run("verify", str(asm))
            self.assertNotEqual(res.returncode, 0)
            for line in ("Missing:              1", "Changed:              1",
                         "Unexpected:           1", "Non-regular:          1"):
                self.assertIn(line, res.stdout)
            bad("check fails on changed target", "check", str(asm))
            bad("report refused on changed target", "report", str(asm))


if __name__ == "__main__":
    unittest.main()
