# ai-code-review-harness

A reusable harness for AI code reviews where every finding is tied to verifiable
evidence. It uses only the Python 3 standard library and never writes to the code under review.

## How it works

1. **Baseline:** hash every file in the target (SHA-256) into an immutable manifest.
   Every later step is checked against it, so findings always refer to a known snapshot.
2. **Evidence:** quoted code is pulled from the target by the tool (path, line range,
   file hash, exact excerpt), never typed out by hand.
3. **Check:** each finding is validated. Its files must be in the baseline, the hashes must match,
   the excerpt must match the file verbatim, the fields must be well formed, and confirmed/rejected
   findings must say how they were verified. The target must still match the baseline.
4. **Validate:** every hypothesis goes to `finding-validator`, which tries to disprove it. Only its
   outcome can make a finding `confirmed`, `rejected` or `runtime_validation`.
5. **Report:** written only when `check` passes. It has confirmed findings, runtime questions, positive
   controls and rejected hypotheses, and it's reproducible (hashes of its inputs, no timestamp).

Agent operating rules (modes, read-only target, historical isolation, workspace, evidence levels, record
formats) are in [CLAUDE.md](CLAUDE.md). Review skills: `.claude/skills/` (review-orchestrator, six
specialists, finding-validator). Start an assessment with `/review-orchestrator`.

## Layout

```
harness.py                     the tool
tests/test_harness.py          self-check
.claude/skills/               orchestrator, specialists, validator
assessments/<project>/         layout and writers: see CLAUDE.md
  baseline/  progress.md  findings/  controls/  runtime/  reports/
```

## Usage

```bash
H="python3 harness.py"
A=assessments/spin

$H baseline $A --target /path/to/target --project SPIN   # once per snapshot
$H verify   $A                                          # target unchanged? exit 0 = PASS
$H evidence $A backend/auth.py 40 52                    # evidence block for a finding
$H check    $A                                          # verify target + validate all findings
$H report   $A -o $A/reports/final.md                   # retained, never overwritten
```

Self-check: `python3 -m unittest discover tests`

## Assessments

| Project | Target | Baseline |
|---|---|---|
| SPIN | `/home/shubhammankodiya/Documents/SPINNMain/SPINN-main` | [assessments/spin/baseline](assessments/spin/baseline/README.md), 1034 files, no git metadata |
