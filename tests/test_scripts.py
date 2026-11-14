"""Tests for the t3-review-loop helper scripts. Run: python3 -m unittest discover -s tests"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "skills", "t3-review-loop", "scripts"))

import conflicts  # noqa: E402
import publish_evidence  # noqa: E402
import select_roles  # noqa: E402
import state  # noqa: E402

with open(os.path.join(ROOT, "tests", "fixtures", "catalog.json"), encoding="utf-8") as source:
    CATALOG = json.load(source)


def roles(**kwargs):
    return select_roles.select_roles([CATALOG], **kwargs)


def model(role):
    return role["target"]["model"]


class SelectRoles(unittest.TestCase):
    def test_defaults_delegate_both_roles_across_vendors(self):
        result = roles()
        self.assertEqual(result["mode"], "coordinator")
        self.assertEqual(result["implementer"]["target"],
                         {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "high"}})
        self.assertEqual(result["reviewer"]["target"],
                         {"providerInstanceId": "cursor", "model": "grok-4.7", "options": {"reasoning_effort": "high"}})
        self.assertEqual(result["independence"], "cross-vendor")
        self.assertTrue(result["needsConfirmation"])

    def test_explicit_roles_need_no_confirmation(self):
        result = roles(implementer="cursor", reviewer="claude")
        self.assertEqual((model(result["implementer"]), model(result["reviewer"])), ("grok-4.7", "claude-opus-5-5"))
        self.assertFalse(result["needsConfirmation"])

    def test_alias_and_unauthenticated_provider(self):
        with self.assertRaisesRegex(select_roles.Blocked, "not authenticated"):
            roles(implementer="gpt")

    def test_bare_token_falls_back_to_model_pattern(self):
        # "grok" is also a disabled driver; the pattern must still find Cursor's Grok.
        self.assertEqual(model(roles(reviewer="grok")["reviewer"]), "grok-4.7")
        self.assertEqual(roles(reviewer="gemini")["reviewer"]["target"]["providerInstanceId"], "cursor")

    def test_version_patterns(self):
        self.assertEqual(model(roles(reviewer="cursor:opus")["reviewer"]), "claude-opus-5-5")
        self.assertEqual(model(roles(reviewer="cursor:opus-5")["reviewer"]), "claude-opus-5")
        self.assertEqual(model(roles(reviewer="cursor:opus-4-8")["reviewer"]), "claude-opus-4-8")
        self.assertEqual(model(roles(reviewer="cursor:grok-4.6")["reviewer"]), "grok-4.6")

    def test_effort(self):
        self.assertEqual(roles(reviewer="claude:sonnet@max")["reviewer"]["target"]["options"], {"effort": "max"})
        with self.assertRaisesRegex(select_roles.Blocked, "does not offer effort"):
            roles(reviewer="gemini@max")
        with self.assertRaisesRegex(select_roles.Blocked, "no effort option"):
            roles(reviewer="cursor:composer@high")

    def test_lead_roles(self):
        self.assertEqual(roles(implementer="lead")["mode"], "lead-implements")
        self.assertEqual(roles(reviewer="lead")["mode"], "lead-reviews")
        with self.assertRaisesRegex(select_roles.Blocked, "separate tasks"):
            roles(implementer="lead", reviewer="lead")

    def test_lead_implementer_gets_another_vendor_as_reviewer(self):
        self.assertEqual(model(roles(implementer="lead")["reviewer"]), "grok-4.7")

    def test_same_model_is_allowed_but_reported(self):
        result = roles(implementer="claude", reviewer="claude")
        self.assertEqual(result["independence"], "same-model")
        self.assertTrue(any("same model" in note for note in result["notes"]))

    def test_unknown_model_hints_at_catalog_search(self):
        with self.assertRaisesRegex(select_roles.Blocked, "search='sol'"):
            roles(reviewer="sol")

    def test_searched_catalog_is_merged(self):
        extra = {"providers": [{"providerInstanceId": "cursor", "models": [{"id": "gpt-6.1-sol", "label": "GPT-6.1-Sol"}]}]}
        result = select_roles.select_roles([CATALOG, extra], reviewer="sol")
        self.assertEqual(result["reviewer"]["target"], {"providerInstanceId": "cursor", "model": "gpt-6.1-sol"})

    def test_config_and_project_override(self):
        config = {"implementer": "cursor", "reviewer": "claude",
                  "projects": {"/repo": {"reviewer": "claude:haiku"}}}
        self.assertEqual(model(roles(config=config)["reviewer"]), "claude-opus-5-5")
        scoped = roles(config=config, project="/repo")
        self.assertEqual(model(scoped["reviewer"]), "claude-haiku-5-5")
        self.assertEqual(scoped["reviewer"]["source"], "project-config")
        self.assertEqual(model(roles(config=config, reviewer="cursor:gemini")["reviewer"]), "gemini-4-carbon")

    def test_wrapped_mcp_result(self):
        wrapped = {"content": [{"type": "text", "text": json.dumps(CATALOG)}]}
        self.assertEqual(select_roles.select_roles([wrapped])["mode"], "coordinator")

    def test_save_keeps_patterns_not_model_ids(self):
        with tempfile.TemporaryDirectory() as scratch:
            config = os.path.join(scratch, "nested", "config.json")
            fixture = os.path.join(ROOT, "tests", "fixtures", "catalog.json")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(select_roles.main([fixture, "--config", config, "--save"]), 0)
            with open(config, encoding="utf-8") as source:
                self.assertEqual(json.load(source), {"implementer": "claudeAgent", "reviewer": "cursor"})


def run_state(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = state.main(list(argv))
    return code, out.getvalue(), err.getvalue()


ISSUE = {"number": 198, "title": "Profile page", "url": "https://example.test/198", "body": """
## Opis
- [ ] not a criterion

## Kryteria akceptacji
- [ ] User sees the avatar
- [x] Coverage is at least 80%

```
- [ ] inside code
```
"""}


def review_block(round_number, head, combined, findings=(), verdicts=("met", "met")):
    return "Prose first.\n```json\n" + json.dumps({
        "schema": "t3-review/1", "round": round_number, "heads": {"change": head},
        "scores": {"combined": combined}, "ci": "not-available", "summary": "Reviewed.",
        "deductions": {"combined": ["F-1-1 is open"]} if combined < 10 else {},
        "findings": list(findings),
        "criteria": [{"id": f"AC-{i + 1}", "verdict": v, "evidence": "checked"} for i, v in enumerate(verdicts)],
    }) + "\n```\n"


def finding(identifier, state_name="open", new=True):
    base = {"id": identifier, "state": state_name}
    if new:
        base.update(severity="P1", title="Avatar leaks", file="a.ts", line=3,
                    trigger="open profile", impact="shows another user", fix="filter by id")
    return base


class StateLoop(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        os.environ["XDG_STATE_HOME"] = self.scratch.name
        code, out, _ = run_state("init", "--repo", self.scratch.name, "--ticket", "198", "--task", "Do it")
        self.assertEqual(code, 0)
        self.run_dir = json.loads(out)["run"]
        issue = os.path.join(self.scratch.name, "issue.json")
        with open(issue, "w", encoding="utf-8") as sink:
            json.dump(ISSUE, sink)
        run_state("criteria", "--run", self.run_dir, "--issue-json", issue)

    def record(self, text, *extra):
        path = os.path.join(self.scratch.name, "answer.md")
        with open(path, "w", encoding="utf-8") as sink:
            sink.write(text)
        return run_state("review", "--run", self.run_dir, "--file", path, *extra)

    def gate(self, head):
        code, out, _ = run_state("gate", "--run", self.run_dir, "--head", head)
        return code, json.loads(out)

    def test_criteria_come_from_the_acceptance_section(self):
        criteria = state.load(self.run_dir)["criteria"]
        self.assertEqual([(c["id"], c["text"]) for c in criteria],
                         [("AC-1", "User sees the avatar"), ("AC-2", "Coverage is at least 80%")])

    def test_full_loop_passes_after_repair(self):
        run_state("set", "--run", self.run_dir, "--visual", "no")
        run_state("round", "--run", self.run_dir, "--head", "aaaaaaa1")
        code, _, err = self.record(review_block(1, "aaaaaaa1", 6, [finding("F-1-1")], ("met", "unmet")))
        self.assertEqual(code, 0, err)
        code, result = self.gate("aaaaaaa1")
        self.assertEqual(code, 1)
        self.assertEqual(len(result["reasons"]), 3)

        run_state("finding", "--run", self.run_dir, "--id", "F-1-1", "--action", "fixed", "--commit", "bbbbbbb2")
        run_state("round", "--run", self.run_dir, "--head", "bbbbbbb2")
        code, _, err = self.record(review_block(2, "bbbbbbb2", 9, [finding("F-1-1", "resolved", new=False)]))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gate("bbbbbbb2")[0], 0)
        # A new commit after the passing review reopens the gate.
        code, result = self.gate("ccccccc3")
        self.assertEqual(code, 1)
        self.assertIn("current head", result["reasons"][0])
        _, report, _ = run_state("report", "--run", self.run_dir)
        self.assertIn("Completed independent reviews: **2**", report)
        self.assertIn("F-1-1", report)

    def test_invalid_reviews_are_rejected(self):
        run_state("round", "--run", self.run_dir, "--head", "aaaaaaa1")
        cases = {
            "commit under review": review_block(1, "fffffff9", 9),
            "round must be 1": review_block(2, "aaaaaaa1", 9),
            "must be named F-1-": review_block(1, "aaaaaaa1", 5, [finding("BUG-7")]),
            "AC-2 has no verdict": review_block(1, "aaaaaaa1", 9, verdicts=("met",)),
            "No valid JSON block": "The code looks fine. Safe To Merge: 9/10",
        }
        for expected, text in cases.items():
            code, _, err = self.record(text)
            self.assertEqual(code, 2)
            self.assertIn(expected, err)
        bad = json.loads(review_block(1, "aaaaaaa1", 9).split("```json\n")[1].split("\n```")[0])
        bad["scores"]["combined"] = 11
        code, _, err = self.record("```json\n" + json.dumps(bad) + "\n```")
        self.assertIn("integer from 0 to 10", err)

    def test_score_below_ten_needs_a_named_reason(self):
        run_state("set", "--run", self.run_dir, "--visual", "no")
        run_state("round", "--run", self.run_dir, "--head", "aaaaaaa1")
        block = json.loads(review_block(1, "aaaaaaa1", 9).split("```json\n")[1].split("\n```")[0])
        del block["deductions"]
        code, _, err = self.record("```json\n" + json.dumps(block) + "\n```")
        self.assertEqual(code, 2)
        self.assertIn("the score is 10", err)
        code, _, err = self.record(review_block(1, "aaaaaaa1", 10))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.gate("aaaaaaa1")[0], 0)

    def test_open_finding_must_be_restated(self):
        run_state("set", "--run", self.run_dir, "--visual", "no")
        run_state("round", "--run", self.run_dir, "--head", "aaaaaaa1")
        self.record(review_block(1, "aaaaaaa1", 6, [finding("F-1-1")]))
        run_state("round", "--run", self.run_dir, "--head", "bbbbbbb2")
        code, _, err = self.record(review_block(2, "bbbbbbb2", 9))
        self.assertEqual(code, 2)
        self.assertIn("F-1-1 is still open", err)

    def test_escalation_on_repeated_dispute_and_round_limit(self):
        run_state("set", "--run", self.run_dir, "--visual", "no", "--max-rounds", "3")
        head = "aaaaaaa1"
        run_state("round", "--run", self.run_dir, "--head", head)
        self.record(review_block(1, head, 7, [finding("F-1-1")]))
        for number in (2, 3):
            code, _, err = run_state("finding", "--run", self.run_dir, "--id", "F-1-1",
                                     "--action", "disputed", "--note", "unreachable: guarded in b.ts")
            self.assertEqual(code, 0, err)
            run_state("round", "--run", self.run_dir, "--head", head)
            self.record(review_block(number, head, 7, [finding("F-1-1", new=False)]))
        code, result = self.gate(head)
        self.assertEqual(code, 3)
        joined = " ".join(result["escalation"])
        self.assertIn("disputed and upheld 2 times", joined)
        self.assertIn("limit is 3", joined)
        self.assertIn("did not improve", joined)
        self.assertEqual(run_state("finding", "--run", self.run_dir, "--id", "F-1-1", "--action", "disputed")[0], 2)

    def test_visual_change_needs_a_screenshot_and_waiver_unblocks_criterion(self):
        shot = os.path.join(self.scratch.name, "AC-1-after.png")
        with open(shot, "wb") as sink:
            sink.write(b"png")
        report = {"schema": "t3-impl/1", "head": "aaaaaaa1", "visualChange": True, "summary": "Done.",
                  "checks": [{"command": "npm test", "result": "passed"}]}
        path = os.path.join(self.scratch.name, "impl.md")
        with open(path, "w", encoding="utf-8") as sink:
            sink.write("```json\n" + json.dumps(report) + "\n```")
        self.assertEqual(run_state("impl", "--run", self.run_dir, "--file", path)[0], 0)
        run_state("round", "--run", self.run_dir, "--head", "aaaaaaa1")
        self.record(review_block(1, "aaaaaaa1", 9, verdicts=("met", "unverified")))
        code, result = self.gate("aaaaaaa1")
        self.assertEqual(code, 1)
        self.assertEqual(len(result["reasons"]), 2)
        run_state("evidence", "--run", self.run_dir, "--path", shot, "--criterion", "AC-1")
        run_state("waive", "--run", self.run_dir, "--criterion", "AC-2", "--reason", "user: measured in CI")
        self.assertEqual(self.gate("aaaaaaa1")[0], 0)
        self.assertTrue(os.path.isfile(os.path.join(self.run_dir, "evidence", "AC-1-after.png")))

    def test_round_cannot_advance_without_a_review(self):
        run_state("round", "--run", self.run_dir, "--head", "aaaaaaa1")
        self.assertEqual(run_state("round", "--run", self.run_dir, "--head", "bbbbbbb2")[0], 2)
        code, out, _ = run_state("round", "--run", self.run_dir, "--head", "bbbbbbb2", "--replace")
        self.assertEqual((code, json.loads(out)["round"]), (0, 1))


class Conflicts(unittest.TestCase):
    def test_conflicts_with_base_and_open_pull_requests(self):
        with tempfile.TemporaryDirectory() as repo:
            os.environ.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.test",
                              GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.test")

            def git(*args):
                return conflicts.git(repo, *args).stdout.strip()

            def commit(branch, name, text):
                git("checkout", "-q", "-B", branch, "main")
                with open(os.path.join(repo, name), "w", encoding="utf-8") as sink:
                    sink.write(text)
                git("add", name)
                git("commit", "-q", "-m", branch)
                return git("rev-parse", "HEAD")

            git("init", "-q", "-b", "main")
            with open(os.path.join(repo, "a.txt"), "w", encoding="utf-8") as sink:
                sink.write("base\n")
            git("add", "a.txt")
            git("commit", "-q", "-m", "base")
            clashing = commit("pr-1", "a.txt", "from pr 1\n")
            unrelated = commit("pr-2", "b.txt", "other\n")
            mine = commit("mine", "a.txt", "from me\n")
            git("checkout", "-q", "main")
            pulls = [{"number": 1, "title": "one", "headRefName": "pr-1", "headRefOid": clashing,
                      "baseRefName": "main", "files": [{"path": "a.txt"}]},
                     {"number": 2, "title": "two", "headRefName": "pr-2", "headRefOid": unrelated,
                      "baseRefName": "main", "files": [{"path": "b.txt"}]}]

            before = conflicts.check(repo, "main", fetch=False, pull_requests=pulls)
            self.assertFalse(before["hasConflicts"])
            after = conflicts.check(repo, "main", head=mine, fetch=False, pull_requests=pulls)
            self.assertTrue(after["hasConflicts"])
            first, second = after["openPullRequests"]
            self.assertEqual(first["conflictsWithHead"], ["a.txt"])
            self.assertEqual(first["sharedFiles"], ["a.txt"])
            self.assertEqual((second["conflictsWithHead"], second["sharedFiles"]), ([], []))
            self.assertEqual(after["head"]["conflictsWithBase"], [])
            self.assertIn("PR #1", after["summary"][0])
            self.assertFalse(conflicts.check(repo, "main", head=mine, fetch=False,
                                             pull_requests=pulls, skip=[1])["hasConflicts"])
            self.assertEqual(git("status", "--porcelain"), "")
            self.assertEqual(git("branch", "--show-current"), "main")


class PublishEvidence(unittest.TestCase):
    def test_commit_on_side_ref_leaves_branch_and_tree_alone(self):
        with tempfile.TemporaryDirectory() as scratch:
            remote, repo = os.path.join(scratch, "remote.git"), os.path.join(scratch, "repo")
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.test",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.test")
            os.environ.update(env)
            subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
            subprocess.run(["git", "init", "-q", repo], check=True)
            git = lambda *args: publish_evidence.git(repo, *args)  # noqa: E731
            git("commit", "-q", "--allow-empty", "-m", "base")
            git("remote", "add", "origin", remote)
            head = git("rev-parse", "HEAD")
            shot = os.path.join(scratch, "after.png")
            with open(shot, "wb") as sink:
                sink.write(b"\x89PNG fake")
            result = publish_evidence.publish(repo, "ticket-198", [shot])
            self.assertEqual(git("rev-parse", "HEAD"), head)
            self.assertEqual(git("status", "--porcelain"), "")
            self.assertEqual(git("ls-tree", "-r", "--name-only", result["commit"]), "ticket-198/after.png")
            pushed = subprocess.run(["git", "-C", remote, "rev-parse", result["ref"]],
                                    capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(pushed, result["commit"])
            self.assertIsNone(result["images"][0]["url"])

    def test_github_slug(self):
        for url in ("https://github.com/o/r.git", "git@github.com:o/r.git", "https://github.com/o/r"):
            self.assertEqual(publish_evidence.github_slug(url), "o/r")
        self.assertIsNone(publish_evidence.github_slug("https://gitlab.com/o/r.git"))


if __name__ == "__main__":
    unittest.main()
