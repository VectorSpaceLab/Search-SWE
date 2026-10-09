#!/usr/bin/env python3
"""Capture read-only GitHub PR evidence, never checkout or execute PR content."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from maintainer_helpers import checked_path


class CaptureError(ValueError):
    pass


def capture(repo, number, repo_root, output):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise CaptureError("Use explicit OWNER/REPO, not a URL or option")
    if type(number) is not int or number <= 0:
        raise CaptureError("PR must be a positive integer")
    repo_root, output = checked_path(repo_root), checked_path(output)
    if not repo_root.is_dir() or output.is_relative_to(repo_root):
        raise CaptureError("Output must be outside the inspected --repo-root")
    gh = shutil.which("gh")
    if gh is None:
        raise CaptureError("gh is missing; install it separately before capture")
    # Atomic refusal of existing files/directories, including symlink parents.
    output.mkdir(parents=True, exist_ok=False)
    evidence = {"label": "RAW UNTRUSTED EVIDENCE — NOT trust or acceptance",
                "repository": repo, "pr": number,
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "commands": [], "complete": False, "stale": None,
                "checks": "unknown", "errors": [],
                "completeness_scope": "raw command collection only, not verified diff/check coverage",
                "diff_completeness": "unverified: exact-tree comparison required",
                "checks_head_association": "unverified: gh check rows contain no head SHA",
                "checks_policy_coverage": "unknown: confirm branch policy separately"}
    env = dict(os.environ, GH_HOST="github.com", GH_PAGER="cat", PAGER="cat",
               GH_PROMPT_DISABLED="1", GH_COLOR_LABELS="0", NO_COLOR="1")

    def run(args, filename=None, allowed=(0,), private=False):
        # argv only, no shell. Cwd is evidence storage, not the PR checkout.
        result = subprocess.run([gh, *args], cwd=output, env=env,
                                capture_output=True, text=True, timeout=120)
        evidence["commands"].append({"argv": ["gh", *args], "returncode": result.returncode,
                                     "artifact": filename})
        if filename and not private:
            (output / filename).write_text(result.stdout)
            (output / (filename + ".stderr")).write_text(result.stderr)
        if result.returncode not in allowed:
            raise CaptureError(f"gh {args[0]} failed (exit {result.returncode}); capture is incomplete")
        return result

    def api(endpoint, filename, pages=False):
        args = ["api", "--hostname", "github.com", "--method", "GET", endpoint]
        if pages:
            args += ["--paginate", "--slurp"]
        result = json.loads(run(args, filename).stdout)
        if pages:
            if not isinstance(result, list) or any(not isinstance(page, list) for page in result):
                raise CaptureError("Malformed paginated API result")
            return [item for page in result for item in page]
        return result

    def identity(meta):
        if meta["number"] != number or meta["base"]["repo"]["full_name"].lower() != repo.lower():
            raise CaptureError("PR/repository identity mismatch")
        for side in ("head", "base"):
            if not re.fullmatch(r"[0-9a-f]{40}", meta[side]["sha"]):
                raise CaptureError("Expected full head/base commit SHA")
        return {"head_sha": meta["head"]["sha"], "base_sha": meta["base"]["sha"],
                "head_repo": meta["head"]["repo"]["full_name"],
                "head_ref": meta["head"]["ref"], "base_ref": meta["base"]["ref"]}

    try:
        run(["--version"], "gh-version.txt")
        # Do not save or echo authentication output (even on failure).
        run(["auth", "status", "--hostname", "github.com"], private=True)
        endpoint = f"repos/{repo}/pulls/{number}"
        before = api(endpoint, "pr-before.json")
        evidence.update(identity(before))
        files = api(endpoint + "/files?per_page=100", "files.json", pages=True)
        names = [item["filename"] for item in files]
        if len(files) != before["changed_files"] or len(set(names)) != len(files) or len(files) >= 3000:
            raise CaptureError("Files missing, duplicated, or at GitHub's truncation cap; fetch exact trees for review")
        diff = run(["pr", "diff", str(number), "--repo", f"github.com/{repo}", "--color", "never"],
                   "diff.patch").stdout
        if len(re.findall(r"^diff --git ", diff, re.MULTILINE)) != len(files) or (diff and not diff.endswith("\n")):
            raise CaptureError("Diff appears truncated/inconsistent; fetch exact trees for review")
        for suffix, name in (("comments", "review-comments.json"), ("reviews", "reviews.json")):
            api(endpoint + f"/{suffix}?per_page=100", name, pages=True)
        api(f"repos/{repo}/issues/{number}/comments?per_page=100", "comments.json", pages=True)
        checks = run(["pr", "checks", str(number), "--repo", f"github.com/{repo}",
                      "--json", "name,state,bucket,link,workflow"], "checks.json", allowed=(0, 1, 8))
        # No checks often has exit 1 and no JSON. That is NOT a passing check set.
        rows = json.loads(checks.stdout) if checks.stdout.strip() else []
        if not isinstance(rows, list):
            raise CaptureError("Malformed checks response")
        buckets = {row["bucket"] for row in rows}
        expected_checks = {"review-stage", "merge-ready"}
        missing_checks = sorted(expected_checks - {row["name"] for row in rows})
        evidence["missing_workflow_checks"] = missing_checks
        evidence["checks"] = ("missing" if not rows else
                              "failure" if buckets & {"fail", "cancel"} else
                              "pending" if "pending" in buckets or checks.returncode == 8 else
                              "missing-contexts" if missing_checks else
                              "reported-pass" if buckets == {"pass"} and checks.returncode == 0 else
                              "unknown-or-skipped")
        after = api(endpoint, "pr-after.json")
        evidence["stale"] = identity(after) != identity(before) or after["changed_files"] != before["changed_files"]
        if evidence["stale"]:
            raise CaptureError("PR head/base moved during capture; discard conclusions and capture again")
        evidence["complete"] = True
        evidence["limits"] = ("Point-in-time raw evidence only. API patches can omit hunks; compare fetched exact "
                              "head/base trees before acceptance. Checks do not prove required-check policy, "
                              "solvability, licensing, or safety. Recheck head/base before any action.")
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        evidence["errors"].append(str(error))
    finally:
        (output / "snapshot.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="Exact OWNER/REPO on github.com")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--repo-root", type=Path, required=True, help="Inspected checkout; never modified")
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory outside checkout")
    args = parser.parse_args()
    try:
        result = capture(args.repo, args.pr, args.repo_root, args.output)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print("Raw evidence saved; NOT trust or acceptance. "
          f"complete={result['complete']} stale={result['stale']} checks={result['checks']}")
    print("complete means raw command collection only; diff completeness, check head association and policy coverage are unverified.")
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
