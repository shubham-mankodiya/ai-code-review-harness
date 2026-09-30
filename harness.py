#!/usr/bin/env python3
"""Evidence-driven code review harness. Stdlib only. Never writes to the target.

Commands (ASSESSMENT = e.g. assessments/spin):
  baseline ASSESSMENT --target DIR --project NAME [--purpose TEXT]
  verify   ASSESSMENT                      target still matches baseline?
  evidence ASSESSMENT PATH START [END]     print an evidence block (JSON) for a record
  check    ASSESSMENT                      verify target + validate findings/, controls/, runtime/
  report   ASSESSMENT [-o FILE]            markdown report (only if check passes)
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

SEVERITIES = ["critical", "high", "medium", "low", "info"]
STATUSES = ["hypothesis", "confirmed", "rejected", "runtime_validation"]
OUTCOMES = {  # validator outcome -> finding status it leads to
    "KEEP": "confirmed", "REWRITE": "confirmed", "DOWNGRADE": "confirmed",
    "RUNTIME_VALIDATION": "runtime_validation", "REJECT": "rejected",
}
VALIDATOR = "finding-validator"
# record kind -> (directory, id letter, required fields)
KINDS = {
    "finding": ("findings", "F", ["id", "title", "severity", "category", "status", "author",
                                  "description", "evidence"]),
    "control": ("controls", "C", ["id", "title", "author", "description", "evidence"]),
    "runtime": ("runtime", "RV", ["id", "question", "why", "how_to_verify", "author", "status"]),
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:  # read-only, always
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(target):
    """(regular files, other non-dir entries) as target-relative paths, byte-sorted."""
    files, other = [], []
    for root, dirs, names in os.walk(target):
        for n in names + [d for d in dirs if os.path.islink(os.path.join(root, d))]:
            full = os.path.join(root, n)
            rel = os.path.relpath(full, target)
            (files if stat.S_ISREG(os.lstat(full).st_mode) else other).append(rel)
    key = os.fsencode
    return sorted(files, key=key), sorted(other, key=key)


def load(assessment):
    base = Path(assessment) / "baseline"
    meta = json.loads((base / "snapshot-metadata.json").read_text())
    manifest = {}
    for line in (base / "manifest.sha256").read_text(encoding="utf-8").splitlines():
        h, p = line.split("  ", 1)
        manifest[p] = h
    return meta, manifest


def read_lines(target, path):
    text = Path(target, path).read_bytes().decode("utf-8", "replace")
    return [l.rstrip("\r") for l in text.split("\n")]


# ---------------------------------------------------------------- commands

def cmd_baseline(a):
    target = Path(a.target).resolve()
    out = Path(a.assessment).resolve() / "baseline"
    if out == target or target in out.parents:
        sys.exit("refusing: baseline output is inside the target")
    if out.exists():
        sys.exit(f"refusing: {out} exists — baselines are immutable, use a new assessment dir")
    files, other = walk(target)
    bad = [p for p in files if "\n" in p or "\\" in p]
    if bad:
        sys.exit(f"refusing: unsupported characters in path names: {bad[:5]}")
    has_git = (target / ".git").exists()
    commit = None
    if has_git:  # rev-parse is read-only
        commit = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    lines = [f"{sha256(target / p)}  {p}\n" for p in files]
    meta = {
        "project": a.project,
        "target": str(target),
        "purpose": a.purpose,
        "hash_algorithm": "SHA-256",
        "file_count": len(files),
        "total_bytes": sum((target / p).stat().st_size for p in files),
        "git_metadata_available": has_git,
        "git_commit": commit,
        "baseline_timestamp": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    out.mkdir(parents=True)
    (out / "manifest.sha256").write_text("".join(lines), encoding="utf-8")
    (out / "snapshot-metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2))
    if other:
        print(f"note: {len(other)} non-regular entries not hashed: {other[:10]}", file=sys.stderr)


def verify(assessment):
    meta, manifest = load(assessment)
    target = meta["target"]
    files, other = walk(target)
    on_disk = set(files)
    missing = sorted(set(manifest) - on_disk)
    unexpected = sorted(on_disk - set(manifest))
    changed = [p for p in manifest if p in on_disk and sha256(os.path.join(target, p)) != manifest[p]]
    return meta, manifest, {"missing": missing, "changed": changed,
                            "unexpected": unexpected, "non_regular": other}


def status_lines(meta, manifest, r):
    ok = not any(r.values())  # a new symlink/device is a change too
    out = ["BASELINE STATUS",
           f"Target:               {meta['target']}",
           f"Baseline:             {meta['baseline_timestamp']} ({len(manifest)} files, {meta['total_bytes']} bytes)"]
    for k in ("missing", "changed", "unexpected", "non_regular"):
        out.append(f"{k.replace('_', '-').capitalize() + ':':<22}{len(r[k])}")
        out += [f"  - {p}" for p in r[k][:20]]
    out.append(f"Overall result:       {'PASS' if ok else 'FAIL'}")
    return ok, out


def cmd_verify(a):
    ok, out = status_lines(*verify(a.assessment))
    print("\n".join(out))
    sys.exit(0 if ok else 1)


def cmd_evidence(a):
    meta, manifest = load(a.assessment)
    path = os.path.normpath(a.path)
    if path not in manifest:
        sys.exit(f"{path} is not in the baseline manifest")
    if sha256(os.path.join(meta["target"], path)) != manifest[path]:
        sys.exit(f"{path} changed since baseline — evidence would not match the assessed snapshot")
    lines = read_lines(meta["target"], path)
    end = a.end or a.start
    if not 1 <= a.start <= end <= len(lines):
        sys.exit(f"line range {a.start}-{end} outside 1-{len(lines)}")
    print(json.dumps({"path": path, "start_line": a.start, "end_line": end,
                      "sha256": manifest[path],
                      "excerpt": "\n".join(lines[a.start - 1:end])}, indent=2))


def check_evidence(blocks, meta, manifest):
    """Evidence integrity only: exact quotes from the baselined snapshot. Not sufficiency."""
    if not isinstance(blocks, list):
        return ["evidence must be a list of evidence blocks"]
    errs = []
    for i, ev in enumerate(blocks):
        tag = f"evidence[{i}]"
        if not isinstance(ev, dict):
            errs.append(f"{tag}: must be an object from `harness.py evidence`")
            continue
        path = ev.get("path")
        if path not in manifest:
            errs.append(f"{tag}: path {path!r} not in baseline manifest")
            continue
        if ev.get("sha256") != manifest[path]:
            errs.append(f"{tag}: sha256 does not match baseline for {path}")
        s, e = ev.get("start_line"), ev.get("end_line")
        lines = read_lines(meta["target"], path)
        if not (isinstance(s, int) and isinstance(e, int) and 1 <= s <= e <= len(lines)):
            errs.append(f"{tag}: bad line range {s}-{e} (file has {len(lines)} lines)")
        elif ev.get("excerpt") != "\n".join(lines[s - 1:e]):
            errs.append(f"{tag}: excerpt does not match {path}:{s}-{e} verbatim")
    return errs


def check_finding(f, runtime_ids):
    """Lifecycle gates: a hypothesis only leaves 'hypothesis' through the validator."""
    errs = []
    if f["severity"] not in SEVERITIES:
        errs.append(f"severity must be one of {SEVERITIES}")
    if f["status"] not in STATUSES:
        return errs + [f"status must be one of {STATUSES}"]
    if f["status"] == "hypothesis":
        return errs
    v = f.get("validation")
    if not isinstance(v, dict) or v.get("by") != VALIDATOR:
        return errs + [f"status '{f['status']}' requires a 'validation' object with by='{VALIDATOR}'"]
    if f["author"] == VALIDATOR:
        errs.append(f"{VALIDATOR} cannot validate a record it authored")
    if OUTCOMES.get(v.get("outcome")) != f["status"]:
        errs.append(f"validation.outcome {v.get('outcome')!r} does not lead to status '{f['status']}'")
    for k in ("disproof_attempts", "ponytail"):
        if not v.get(k):
            errs.append(f"validation.{k} is required")
    if f["status"] == "confirmed":
        for k in ("call_path", "controls_checked", "impact"):
            if not f.get(k):
                errs.append(f"confirmed finding requires '{k}'")
        lvl = f.get("evidence_level")
        if lvl not in (1, 2, 3, 4, 5):
            errs.append("confirmed finding requires evidence_level 1-5")
        elif f["severity"] in ("critical", "high") and lvl < 4 and not f.get("level_justification"):
            errs.append(f"{f['severity']} finding at evidence_level {lvl} needs level 4+ or 'level_justification'")
    if f["status"] == "runtime_validation" and f.get("runtime_item") not in runtime_ids:
        errs.append(f"runtime_item {f.get('runtime_item')!r} does not exist in runtime/")
    return errs


def check(assessment):
    """(ok, output lines, meta, {kind: [records]})"""
    meta, manifest, r = verify(assessment)
    ok, out = status_lines(meta, manifest, r)
    records = {k: [] for k in KINDS}
    for kind, (sub, letter, required) in KINDS.items():
        for p in sorted((Path(assessment) / sub).glob("*.json")):
            try:
                rec = json.loads(p.read_text())
            except json.JSONDecodeError as e:
                errs = [f"invalid JSON: {e}"]
            else:
                errs = [f"missing field '{k}'" for k in required if not rec.get(k)]
                if not errs:
                    if rec["id"] != p.stem:
                        errs.append(f"id '{rec['id']}' does not match file name")
                    if not re.fullmatch(rf"{letter}-[A-Z0-9]+-\d{{3}}", p.stem):
                        errs.append(f"file name must look like {letter}-<PREFIX>-001.json")
                    if "evidence" in rec:
                        errs += check_evidence(rec["evidence"], meta, manifest)
                    records[kind].append(rec)
            out += [f"{sub}/{p.name}: {e}" for e in errs]
            ok = ok and not errs
    runtime_ids = {r["id"] for r in records["runtime"]}
    for f in records["finding"]:
        errs = check_finding(f, runtime_ids)
        out += [f"findings/{f['id']}.json: {e}" for e in errs]
        ok = ok and not errs
    counts = ", ".join(f"{len(v)} {k}" for k, v in records.items())
    out.append(f"Records checked:      {counts}  ->  {'PASS' if ok else 'FAIL'}")
    return ok, out, meta, records


def cmd_check(a):
    ok, out, _, _ = check(a.assessment)
    print("\n".join(out))
    sys.exit(0 if ok else 1)


def cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def fenced(text):
    fence = "````" if "```" in text else "```"
    return [fence, text, fence]


def evidence_md(blocks):
    out = []
    for ev in blocks:
        out += [f"`{ev['path']}:{ev['start_line']}-{ev['end_line']}` (sha256 `{ev['sha256'][:12]}`)", "",
                *fenced(ev["excerpt"]), ""]
    return out


def cmd_report(a):
    ok, log, meta, rec = check(a.assessment)
    if not ok:
        sys.stderr.write("\n".join(log) + "\n")
        sys.exit("report refused: check failed")
    if a.output and Path(a.output).exists():
        sys.exit(f"refusing: {a.output} exists — reports are retained, pick a new name")
    fs = rec["finding"]
    confirmed = sorted((f for f in fs if f["status"] == "confirmed"),
                       key=lambda f: (SEVERITIES.index(f["severity"]), f["id"]))
    n = {s: sum(f["status"] == s for f in fs) for s in STATUSES}
    base = Path(a.assessment) / "baseline" / "manifest.sha256"
    # no timestamp: the same inputs always produce the same bytes
    inputs = hashlib.sha256()
    for kind in KINDS:
        for r in sorted(rec[kind], key=lambda r: r["id"]):
            inputs.update(json.dumps(r, sort_keys=True).encode())
    out = [f"# {meta['project']} — Code Review Report", "",
           f"- Target: `{meta['target']}`",
           f"- Baseline: {meta['baseline_timestamp']} — {meta['file_count']} files, "
           f"git commit: {meta['git_commit'] or 'none (no git metadata)'}",
           "- Target verified against baseline: PASS",
           f"- Reproducibility: manifest sha256 `{sha256(base)}`, harness sha256 `{sha256(__file__)}`, "
           f"records sha256 `{inputs.hexdigest()}`",
           f"- Findings: {n['confirmed']} confirmed, {n['runtime_validation']} need runtime validation, "
           f"{n['rejected']} rejected, {n['hypothesis']} unvalidated hypotheses (excluded)", "",
           "## Confirmed findings", "",
           "| ID | Severity | Evidence level | Category | Title |", "|---|---|---|---|---|"]
    out += [f"| {f['id']} | {f['severity']} | {f['evidence_level']} | {cell(f['category'])} | {cell(f['title'])} |"
            for f in confirmed]
    for f in confirmed:
        v = f["validation"]
        out += ["", f"### {f['id']}: {f['title']}", "",
                f"**Severity:** {f['severity']} · **Category:** {f['category']} · "
                f"**Evidence level:** {f['evidence_level']} · **Validator outcome:** {v['outcome']}", "",
                f["description"], "", *evidence_md(f["evidence"]),
                f"**Call path:** {f['call_path']}", "",
                f"**Controls checked:** {f['controls_checked']}", "",
                f"**Impact:** {f['impact']}", "",
                f"**Adversarial review:** {v['disproof_attempts']}"]
        if f.get("recommendation"):
            out += ["", f"**Recommendation:** {f['recommendation']}"]
    out += ["", "## Runtime validation required (not source-code findings)", ""]
    out += [f"- **{r['id']}** [{r['status']}] {r['question']} — {r['why']} *Verify:* {r['how_to_verify']}"
            for r in sorted(rec["runtime"], key=lambda r: r["id"])] or ["None."]
    out += ["", "## Positive controls", ""]
    for c in sorted(rec["control"], key=lambda r: r["id"]):
        out += [f"### {c['id']}: {c['title']}", "", c["description"], "", *evidence_md(c["evidence"])]
    if not rec["control"]:
        out.append("None recorded.")
    rejected = [f for f in fs if f["status"] == "rejected"]
    out += ["", "## Rejected hypotheses", ""]
    out += [f"- {f['id']}: {cell(f['title'])} — {f['validation']['disproof_attempts']}" for f in rejected] or ["None."]
    text = "\n".join(out) + "\n"
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        with open(a.output, "x") as fh:  # exclusive create: never overwrite a retained report
            fh.write(text)
        print(f"wrote {a.output}")
    else:
        sys.stdout.write(text)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("assessment")
    b.add_argument("--target", required=True)
    b.add_argument("--project", required=True)
    b.add_argument("--purpose", default="Assessment baseline")
    for name in ("verify", "check"):
        sub.add_parser(name).add_argument("assessment")
    r = sub.add_parser("report")
    r.add_argument("assessment")
    r.add_argument("-o", "--output", help="write here, e.g. assessments/<p>/reports/final.md (never overwrites)")
    e = sub.add_parser("evidence")
    e.add_argument("assessment")
    e.add_argument("path")
    e.add_argument("start", type=int)
    e.add_argument("end", type=int, nargs="?")
    a = p.parse_args()
    globals()["cmd_" + a.cmd](a)


if __name__ == "__main__":
    main()
