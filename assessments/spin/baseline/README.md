# SPIN — Assessment Baseline

Target: `/home/shubhammankodiya/Documents/SPINNMain/SPINN-main`
Baseline taken: 2026-09-30T07:21:50Z (UTC) — 1034 regular files, 95,327,787 bytes.

## Why this baseline exists

Any assessment of SPINN-main is only meaningful if everyone knows exactly which
code was assessed. This baseline pins the target's content at a single point in
time so that every later finding, report, or re-check can be tied to — and
checked against — this exact snapshot.

## No Git metadata

SPINN-main contains no `.git` directory (none at the root or in any
subdirectory). There is no commit hash, branch, or history to identify the
snapshot, so `git_commit` is `null` and `git_metadata_available` is `false` in
`snapshot-metadata.json`. The content hashes in `manifest.sha256` are the only
identity this snapshot has.

## How `manifest.sha256` was produced

Run from inside the target directory, read-only:

```bash
cd /home/shubhammankodiya/Documents/SPINNMain/SPINN-main
find . -type f -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum -- > manifest.sha256
```

- Every regular file is included (hidden files and `.claude/` too). The target
  had no symlinks, devices, sockets, or FIFOs at baseline time.
- Paths are relative to SPINN-main, with no `./` prefix.
- Ordering is deterministic: byte-wise (`LC_ALL=C`) sort of the paths.
- Format is standard GNU coreutils `sha256sum` output (`<hash>  <path>`).
  No file names contained newlines or backslashes, so no line is escaped.
- The filesystem is mounted `noatime`, so hashing did not change access times;
  content and modification times were not touched.

## How to verify the target later

```bash
B=/home/shubhammankodiya/Documents/SPINNMain/ai-code-review-harness/assessments/spin/baseline
cd /home/shubhammankodiya/Documents/SPINNMain/SPINN-main

# 1. Changed or missing files (prints only failures)
sha256sum --quiet -c "$B/manifest.sha256"

# 2. Unexpected (added) files, and missing ones, by path
diff <(cut -c67- "$B/manifest.sha256") \
     <(find . -type f -printf '%P\n' | LC_ALL=C sort)
```

Both commands print nothing and exit 0 when the target is unchanged.
In the `diff` output, `<` lines are missing files and `>` lines are unexpected ones.

## What a changed hash means

A hash mismatch, a missing file, or an unexpected file means the assessment
target has changed since this baseline was taken. Findings made against this
baseline may no longer apply to the current code. Do not silently carry on:
either re-baseline (and record why) or restore the target to match this
manifest before continuing the assessment.
