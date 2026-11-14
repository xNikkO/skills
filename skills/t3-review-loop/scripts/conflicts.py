#!/usr/bin/env python3
"""Report merge conflicts before a ticket starts and before its PR is opened.

Without --head: is the base fresh, and which open PRs already conflict with it.
With --head: would this commit conflict with the base or with any open PR.
Nothing is merged, checked out or pushed; conflicts are computed with
`git merge-tree`, which writes no files and moves no branch.
"""

import argparse
import json
import subprocess
import sys


def git(repo, *args, check=True):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result


def conflicts_between(repo, first, second):
    """Files that conflict when `first` and `second` are merged; [] when clean."""
    result = git(repo, "merge-tree", "--write-tree", "--name-only", first, second, check=False)
    if result.returncode == 0:
        return []
    if result.returncode != 1:
        raise RuntimeError(f"git merge-tree failed: {result.stderr.strip()}")
    files = []
    for line in result.stdout.splitlines()[1:]:
        if not line.strip():
            break
        files.append(line)
    return files or ["(conflict reported without a file name)"]


def has_object(repo, sha):
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0


def open_pull_requests(repo):
    result = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--limit", "100",
         "--json", "number,title,url,headRefName,headRefOid,baseRefName,files"],
        capture_output=True, text=True, cwd=repo)
    if result.returncode != 0:
        raise RuntimeError(f"gh pr list failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def check(repo, base, *, head=None, remote="origin", fetch=True, pull_requests=None, skip=()):
    if fetch:
        git(repo, "fetch", "-q", remote, base)
    remote_base = f"{remote}/{base}"
    if git(repo, "rev-parse", "-q", "--verify", remote_base, check=False).returncode != 0:
        remote_base = base
    base_sha = git(repo, "rev-parse", remote_base).stdout.strip()
    summary = []
    behind = None
    if git(repo, "rev-parse", "-q", "--verify", f"refs/heads/{base}", check=False).returncode == 0:
        behind = int(git(repo, "rev-list", "--count", f"refs/heads/{base}..{base_sha}").stdout.strip())
        if behind:
            summary.append(f"Local {base} is {behind} commit(s) behind {remote_base}; build on {base_sha[:9]}.")

    report = {"base": {"ref": remote_base, "sha": base_sha, "localBehind": behind}, "head": None}
    changed = set()
    if head:
        head_sha = git(repo, "rev-parse", head).stdout.strip()
        with_base = conflicts_between(repo, base_sha, head_sha)
        merge_base = git(repo, "merge-base", base_sha, head_sha).stdout.strip()
        changed = set(git(repo, "diff", "--name-only", merge_base, head_sha).stdout.split("\n")) - {""}
        report["head"] = {"sha": head_sha, "conflictsWithBase": with_base}
        if with_base:
            summary.append(f"The change conflicts with {remote_base} in: {', '.join(with_base)}.")

    if pull_requests is None:
        pull_requests = open_pull_requests(repo)
    entries = []
    for pull in pull_requests:
        if pull.get("number") in skip or (pull.get("baseRefName") or base) != base:
            continue
        sha = pull.get("headRefOid")
        if not has_object(repo, sha) and fetch:
            git(repo, "fetch", "-q", remote, f"refs/pull/{pull['number']}/head", check=False)
        entry = {"number": pull.get("number"), "title": pull.get("title"), "url": pull.get("url"),
                 "branch": pull.get("headRefName"), "conflictsWithBase": None, "conflictsWithHead": None,
                 "sharedFiles": []}
        files = {f.get("path") for f in pull.get("files") or [] if isinstance(f, dict)}
        if has_object(repo, sha):
            entry["conflictsWithBase"] = conflicts_between(repo, base_sha, sha)
            if entry["conflictsWithBase"]:
                summary.append(f"PR #{entry['number']} already conflicts with {remote_base} in: "
                               f"{', '.join(entry['conflictsWithBase'])}.")
            if head:
                entry["conflictsWithHead"] = conflicts_between(repo, report["head"]["sha"], sha)
                if entry["conflictsWithHead"]:
                    summary.append(f"The change and PR #{entry['number']} ({entry['branch']}) conflict in: "
                                   f"{', '.join(entry['conflictsWithHead'])}. Whichever merges second needs a rebase.")
        else:
            summary.append(f"PR #{entry['number']}: its head {str(sha)[:9]} is not available locally; not checked.")
        entry["sharedFiles"] = sorted(changed & files)
        entries.append(entry)
    report["openPullRequests"] = entries
    report["hasConflicts"] = bool(
        (report["head"] and report["head"]["conflictsWithBase"])
        or any(e["conflictsWithBase"] or e["conflictsWithHead"] for e in entries))
    report["summary"] = summary
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--base", required=True, help="Base branch name, such as main")
    parser.add_argument("--head", help="Commit to test; omit for the check before a ticket starts")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--no-fetch", action="store_true")
    parser.add_argument("--skip-pr", type=int, action="append", default=[], help="PR number to leave out, such as the PR under repair")
    parser.add_argument("--prs-json", help="Open PRs as JSON instead of asking gh")
    args = parser.parse_args(argv)
    try:
        pulls = None
        if args.prs_json:
            with open(args.prs_json, encoding="utf-8") as source:
                pulls = json.load(source)
        report = check(args.repo, args.base, head=args.head, remote=args.remote, fetch=not args.no_fetch,
                       pull_requests=pulls, skip=args.skip_pr)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Conflict check blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["hasConflicts"] else 0


if __name__ == "__main__":
    sys.exit(main())
