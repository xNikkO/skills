#!/usr/bin/env python3
"""Publish screenshots for a pull request without adding them to its branch.

The files are committed to a side ref (refs/t3-review-loop/evidence/<name>) that
no branch contains, pushed, and printed as Markdown image links pinned to that
commit. The working tree, the index and the checked-out branch are not touched.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile


def git(repo, *args, env=None, stdin=None):
    result = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                            env=env, input=stdin)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def github_slug(url):
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def publish(repo, name, files, *, remote="origin", push=True):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise RuntimeError("The evidence name may only contain letters, digits, dots, dashes and underscores.")
    names = [os.path.basename(path) for path in files]
    if len(set(names)) != len(names):
        raise RuntimeError("Evidence file names must be unique.")
    for path in files:
        if not os.path.isfile(path):
            raise RuntimeError(f"Evidence file does not exist: {path}")
    with tempfile.TemporaryDirectory() as scratch:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(scratch, "index"))
        for path, base in zip(files, names):
            blob = git(repo, "hash-object", "-w", os.path.abspath(path))
            git(repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{name}/{base}", env=env)
        tree = git(repo, "write-tree", env=env)
    commit = git(repo, "commit-tree", tree, "-m", f"Review evidence for {name}")
    ref = f"refs/t3-review-loop/evidence/{name}"
    git(repo, "update-ref", ref, commit)
    slug = github_slug(git(repo, "remote", "get-url", remote))
    if push:
        git(repo, "push", "--force", remote, f"{ref}:{ref}")
    images = []
    for path, base in zip(files, names):
        url = f"https://github.com/{slug}/blob/{commit}/{name}/{base}?raw=true" if slug else None
        images.append({"file": path, "url": url,
                       "markdown": f"![{os.path.splitext(base)[0]}]({url})" if url else None})
    return {"commit": commit, "ref": ref, "pushed": push, "repository": slug, "images": images}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True, help="Local checkout of the repository that hosts the PR")
    parser.add_argument("--name", required=True, help="Folder and ref name, such as the run ID or pr-123")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--no-push", action="store_true", help="Create the commit and ref locally only")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    try:
        result = publish(args.repo, args.name, args.files, remote=args.remote, push=not args.no_push)
    except (OSError, RuntimeError) as error:
        print(f"Evidence publication blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
