#!/usr/bin/env python3
"""Keep the state of one T3 review loop in a file outside the repository.

The lead records every step here so the loop survives context compaction:
criteria, rounds, delegate reports, findings, evidence and the gate decision.
Run `state.py <command> --help` for the arguments of each command.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sys

SEVERITIES = ("P0", "P1", "P2", "P3")
BLOCKING = ("P0", "P1", "P2")
REVIEW_STATES = ("open", "resolved", "rejected")
CLOSED = ("resolved", "rejected", "waived")
VERDICTS = ("met", "unmet", "unverified")
CI = ("pending", "passed", "failed", "not-available")
CRITERIA_HEADING = re.compile(r"accept|criteria|kryteri|definition of done|\bdod\b", re.I)
CHECKBOX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[[ xX]\]\s+(.+?)\s*$")


class Invalid(ValueError):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_root():
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, "t3-review-loop")


def repo_dir(repo):
    repo = os.path.abspath(repo)
    digest = hashlib.sha1(repo.encode()).hexdigest()[:8]
    return os.path.join(state_root(), f"{os.path.basename(repo)}-{digest}")


def load(run):
    with open(os.path.join(run, "state.json"), encoding="utf-8") as source:
        return json.load(source)


def save(run, state):
    state["updatedAt"] = now()
    path = os.path.join(run, "state.json")
    with open(path + ".tmp", "w", encoding="utf-8") as sink:
        json.dump(state, sink, ensure_ascii=False, indent=2)
        sink.write("\n")
    os.replace(path + ".tmp", path)


def read_text(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as source:
        return source.read()


def extract_json(text):
    """The last ```json block of a delegate's answer, or the whole text."""
    blocks = re.findall(r"```json\s*\n(.*?)```", text, re.S)
    for candidate in reversed(blocks):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    try:
        return json.loads(text)
    except ValueError:
        raise Invalid("No valid JSON block found. The answer must end with one ```json fenced block.")


def parse_criteria(body):
    """Checkbox items of an issue body; those under an acceptance heading win."""
    preferred, everything, under_heading, fenced = [], [], False, False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if heading:
            under_heading = bool(CRITERIA_HEADING.search(heading.group(1)))
            continue
        item = CHECKBOX.match(line)
        if item:
            everything.append(item.group(1))
            if under_heading:
                preferred.append(item.group(1))
    return preferred or everything


def same_sha(first, second):
    first, second = str(first).lower(), str(second).lower()
    return len(first) >= 7 and len(second) >= 7 and (first.startswith(second) or second.startswith(first))


def parse_heads(values):
    heads = {}
    for value in values:
        name, separator, sha = value.partition("=")
        if not separator:
            name, sha = "change", value
        heads[name] = sha
    return heads


def current_round(state):
    if not state["rounds"]:
        raise Invalid("No round has been started. Run `state.py round` first.")
    return state["rounds"][-1]


def require(condition, message, errors):
    if not condition:
        errors.append(message)


# ---------------------------------------------------------------- commands


def cmd_init(args):
    directory = repo_dir(args.repo)
    label = f"ticket-{args.ticket}" if args.ticket else "task"
    run = os.path.join(directory, f"{label}-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}")
    os.makedirs(os.path.join(run, "evidence"))
    task = read_text(args.task_file) if args.task_file else (args.task or "")
    state = {
        "schema": "t3-review-loop/1",
        "createdAt": now(),
        "repo": os.path.abspath(args.repo),
        "task": task,
        "ticket": args.ticket,
        "publish": args.publish,
        "threshold": args.threshold,
        "maxRounds": args.max_rounds,
        "visual": None,
        "roles": json.loads(read_text(args.roles)) if args.roles else None,
        "criteria": [],
        "findings": {},
        "rounds": [],
        "evidence": [],
        "pullRequests": [],
        "notes": [],
    }
    save(run, state)
    print(json.dumps({"run": run}, indent=2))


def cmd_list(args):
    directory = repo_dir(args.repo)
    runs = []
    for name in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        run = os.path.join(directory, name)
        try:
            state = load(run)
        except (OSError, ValueError):
            continue
        runs.append({"run": run, "ticket": state.get("ticket"), "rounds": len(state["rounds"]),
                     "finished": state.get("finished"), "updatedAt": state.get("updatedAt")})
    print(json.dumps(runs, indent=2))


def cmd_criteria(args):
    state = load(args.run)
    texts = []
    if args.issue_json:
        issue = json.loads(read_text(args.issue_json))
        texts += [(text, "ticket") for text in parse_criteria(issue.get("body") or "")]
        state["ticketInfo"] = {key: issue.get(key) for key in ("number", "title", "url")}
    texts += [(text, "added") for text in args.add or []]
    known = {c["text"] for c in state["criteria"]}
    for text, source in texts:
        if text in known:
            continue
        known.add(text)
        state["criteria"].append({"id": f"AC-{len(state['criteria']) + 1}", "text": text,
                                  "source": source, "waived": None})
    save(args.run, state)
    print(json.dumps(state["criteria"], ensure_ascii=False, indent=2))


def cmd_round(args):
    state = load(args.run)
    heads = parse_heads(args.head)
    if state["rounds"] and not state["rounds"][-1].get("review") and not args.replace:
        raise Invalid(f"Round {state['rounds'][-1]['n']} has no recorded review yet. Record it, or pass --replace "
                      "to restart that round on a new head.")
    if state["rounds"] and not state["rounds"][-1].get("review"):
        state["rounds"].pop()
    number = len(state["rounds"]) + 1
    directory = os.path.join(args.run, "rounds", str(number))
    os.makedirs(directory, exist_ok=True)
    entry = {"n": number, "startedAt": now(), "heads": heads, "base": args.base, "attempts": [], "review": None}
    state["rounds"].append(entry)
    save(args.run, state)
    print(json.dumps({"round": number, "dir": directory,
                      "clientRequestId": f"{os.path.basename(args.run)}-review-r{number}-a1"}, indent=2))


def cmd_attempt(args):
    state = load(args.run)
    entry = current_round(state)
    entry["attempts"].append({"clientRequestId": args.client_request_id, "taskId": args.task_id,
                              "model": args.model, "outcome": args.outcome, "at": now()})
    save(args.run, state)
    print(json.dumps({"round": entry["n"], "attempts": len(entry["attempts"]),
                      "nextClientRequestId": f"{os.path.basename(args.run)}-review-r{entry['n']}-a{len(entry['attempts']) + 1}"},
                     indent=2))


def validate_review(state, entry, review):
    errors = []
    require(review.get("schema") == "t3-review/1", 'schema must be "t3-review/1"', errors)
    require(review.get("round") == entry["n"], f"round must be {entry['n']}", errors)
    heads = review.get("heads")
    if not isinstance(heads, dict):
        errors.append("heads must map each reviewed scope to its commit SHA")
    else:
        for name, sha in entry["heads"].items():
            require(name in heads and same_sha(heads[name], sha),
                    f"heads.{name} must be the commit under review, {sha}", errors)
    scores = review.get("scores") if isinstance(review.get("scores"), dict) else {}

    def is_score(value):
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10
    require(is_score(scores.get("combined")), "scores.combined must be an integer from 0 to 10", errors)
    scopes = scores.get("scopes") or {}
    if len(entry["heads"]) > 1:
        for name in entry["heads"]:
            require(is_score(scopes.get(name)), f"scores.scopes.{name} must be an integer from 0 to 10", errors)
    for name, score in dict(scopes, combined=scores.get("combined")).items():
        if is_score(score) and score < 10:
            reasons = (review.get("deductions") or {}).get(name) if isinstance(review.get("deductions"), dict) else None
            require(isinstance(reasons, list) and reasons and all(isinstance(r, str) and r.strip() for r in reasons),
                    f"scores.{name} is {score}: deductions.{name} must name each finding or evidence gap that "
                    "costs a point; with nothing concrete to name, the score is 10", errors)
    require(review.get("ci") in CI, f"ci must be one of {', '.join(CI)}", errors)
    require(isinstance(review.get("summary"), str) and review["summary"].strip(), "summary is required", errors)

    seen = set()
    findings = review.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list (empty when there are none)")
        findings = []
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("id"), str):
            errors.append("every finding needs an id")
            continue
        identifier = finding["id"]
        require(identifier not in seen, f"{identifier} is listed twice", errors)
        seen.add(identifier)
        require(finding.get("state") in REVIEW_STATES,
                f"{identifier}: state must be one of {', '.join(REVIEW_STATES)}", errors)
        if identifier in state["findings"]:
            continue
        require(re.fullmatch(rf"F-{entry['n']}-\d+", identifier) is not None,
                f"{identifier}: a finding first reported in this round must be named F-{entry['n']}-<n>", errors)
        require(finding.get("severity") in SEVERITIES,
                f"{identifier}: severity must be one of {', '.join(SEVERITIES)}", errors)
        for field in ("title", "file", "trigger", "impact", "fix"):
            require(isinstance(finding.get(field), str) and finding[field].strip(),
                    f"{identifier}: {field} is required", errors)
    for identifier, known in state["findings"].items():
        require(known["state"] in CLOSED or identifier in seen,
                f"{identifier} is still {known['state']}: restate it as open, resolved or rejected", errors)

    verdicts = review.get("criteria")
    if not isinstance(verdicts, list):
        errors.append("criteria must be a list (empty when the task has none)")
        verdicts = []
    by_id = {v.get("id"): v for v in verdicts if isinstance(v, dict)}
    known_ids = {c["id"] for c in state["criteria"]}
    for identifier in by_id:
        require(identifier in known_ids, f"criteria: unknown id {identifier}", errors)
    for criterion in state["criteria"]:
        verdict = by_id.get(criterion["id"])
        if verdict is None:
            errors.append(f"{criterion['id']} has no verdict")
            continue
        require(verdict.get("verdict") in VERDICTS,
                f"{criterion['id']}: verdict must be one of {', '.join(VERDICTS)}", errors)
        require(isinstance(verdict.get("evidence"), str) and verdict["evidence"].strip(),
                f"{criterion['id']}: evidence is required", errors)
    return errors


def cmd_review(args):
    state = load(args.run)
    entry = current_round(state)
    if entry.get("review") and not args.replace:
        raise Invalid(f"Round {entry['n']} already has a review. Start the next round, or pass --replace.")
    text = read_text(args.file)
    review = extract_json(text)
    errors = validate_review(state, entry, review)
    if errors:
        raise Invalid("The review block is invalid:\n- " + "\n- ".join(errors))
    for finding in review["findings"]:
        identifier = finding["id"]
        known = state["findings"].get(identifier)
        if known is None:
            known = state["findings"][identifier] = {
                "id": identifier, "round": entry["n"], "disputes": 0, "history": [],
                **{key: finding.get(key) for key in
                   ("severity", "title", "file", "line", "trigger", "impact", "fix", "evidence")},
            }
        elif finding["state"] == "open" and known["state"] == "disputed":
            known["disputes"] += 1
        if finding.get("severity") in SEVERITIES:
            known["severity"] = finding["severity"]
        known["state"] = finding["state"]
        known["history"].append({"round": entry["n"], "by": "reviewer", "state": finding["state"],
                                 "note": finding.get("note") or finding.get("evidence")})
    entry["review"] = {
        "recordedAt": now(), "taskId": args.task_id, "model": args.model,
        "scores": review["scores"], "deductions": review.get("deductions") or {},
        "ci": review["ci"], "summary": review["summary"],
        "criteria": review["criteria"], "checks": review.get("checks") or [],
        "findings": [f["id"] for f in review["findings"]],
    }
    directory = os.path.join(args.run, "rounds", str(entry["n"]))
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "review.md"), "w", encoding="utf-8") as sink:
        sink.write(text)
    save(args.run, state)
    print(json.dumps(gate(state, entry["heads"]), ensure_ascii=False, indent=2))


def add_evidence(run, state, path, label, kind, criterion):
    if not os.path.isfile(path):
        raise Invalid(f"Evidence file does not exist: {path}")
    name = os.path.basename(path)
    target = os.path.join(run, "evidence", name)
    if os.path.abspath(path) != os.path.abspath(target):
        stem, extension = os.path.splitext(name)
        counter = 1
        while os.path.exists(target):
            counter += 1
            target = os.path.join(run, "evidence", f"{stem}-{counter}{extension}")
        shutil.copyfile(path, target)
    state["evidence"].append({"path": target, "label": label, "kind": kind, "criterion": criterion,
                              "round": len(state["rounds"]) + 1, "at": now()})
    return target


def respond(state, identifier, action, note, commit, by):
    known = state["findings"].get(identifier)
    if known is None:
        raise Invalid(f"Unknown finding {identifier}.")
    if action not in ("fixed", "disputed", "waived"):
        raise Invalid(f"{identifier}: action must be fixed, disputed or waived.")
    if action == "disputed" and not (note or "").strip():
        raise Invalid(f"{identifier}: a dispute needs its evidence in the note.")
    known["state"] = action
    known["history"].append({"round": len(state["rounds"]), "by": by, "state": action,
                             "note": note, "commit": commit})


def cmd_impl(args):
    state = load(args.run)
    text = read_text(args.file)
    report = extract_json(text)
    errors = []
    require(report.get("schema") == "t3-impl/1", 'schema must be "t3-impl/1"', errors)
    require(isinstance(report.get("head"), str) and len(report["head"]) >= 7, "head must be the commit SHA", errors)
    require(isinstance(report.get("visualChange"), bool), "visualChange must be true or false", errors)
    require(isinstance(report.get("checks"), list) and report["checks"],
            "checks must list what was actually run, including the functional check", errors)
    require(isinstance(report.get("summary"), str) and report["summary"].strip(), "summary is required", errors)
    for item in report.get("evidence") or []:
        require(isinstance(item, dict) and os.path.isfile(str(item.get("path"))),
                f"evidence file is missing: {item.get('path') if isinstance(item, dict) else item}", errors)
    if errors:
        raise Invalid("The implementer block is invalid:\n- " + "\n- ".join(errors))
    for response in report.get("responses") or []:
        respond(state, response.get("id"), response.get("action"), response.get("note"),
                response.get("commit"), "implementer")
    for item in report.get("evidence") or []:
        add_evidence(args.run, state, item["path"], item.get("label") or os.path.basename(item["path"]),
                     item.get("kind") or "screenshot", item.get("criterion"))
    if report["visualChange"] or state["visual"] is None:
        state["visual"] = report["visualChange"]
    state.setdefault("implementation", []).append({
        "recordedAt": now(), "taskId": args.task_id, "threadId": args.thread_id, "model": args.model,
        "head": report["head"], "branch": report.get("branch"), "worktree": report.get("worktree"),
        "checks": report["checks"], "summary": report["summary"],
    })
    number = len(state["implementation"])
    with open(os.path.join(args.run, f"implementation-{number}.md"), "w", encoding="utf-8") as sink:
        sink.write(text)
    save(args.run, state)
    print(json.dumps({"head": report["head"], "visual": state["visual"],
                      "evidence": [e["path"] for e in state["evidence"]]}, indent=2))


def cmd_finding(args):
    state = load(args.run)
    respond(state, args.id, args.action, args.note, args.commit, args.by)
    save(args.run, state)
    print(json.dumps(state["findings"][args.id], ensure_ascii=False, indent=2))


def cmd_waive(args):
    state = load(args.run)
    criterion = next((c for c in state["criteria"] if c["id"] == args.criterion), None)
    if criterion is None:
        raise Invalid(f"Unknown criterion {args.criterion}.")
    criterion["waived"] = args.reason
    save(args.run, state)
    print(json.dumps(criterion, ensure_ascii=False, indent=2))


def cmd_evidence(args):
    state = load(args.run)
    target = add_evidence(args.run, state, args.path, args.label or os.path.basename(args.path),
                          args.kind, args.criterion)
    save(args.run, state)
    print(json.dumps({"path": target}, indent=2))


def cmd_set(args):
    state = load(args.run)
    if args.visual:
        state["visual"] = args.visual == "yes"
    if args.max_rounds:
        state["maxRounds"] = args.max_rounds
    if args.threshold:
        state["threshold"] = args.threshold
    if args.pull_request:
        if args.pull_request not in state["pullRequests"]:
            state["pullRequests"].append(args.pull_request)
    if args.note:
        state["notes"].append({"at": now(), "text": args.note})
    if args.finished:
        state["finished"] = args.finished
    save(args.run, state)
    print(json.dumps({key: state.get(key) for key in
                      ("visual", "maxRounds", "threshold", "pullRequests", "finished")}, indent=2))


def gate(state, heads=None):
    """Decide pass / continue / escalate from recorded facts only."""
    reasons, escalation = [], []
    reviewed = [r for r in state["rounds"] if r.get("review")]
    latest = state["rounds"][-1] if state["rounds"] else None
    threshold = state["threshold"]
    if latest is None or not latest.get("review"):
        reasons.append("The current round has no recorded review.")
    else:
        review = latest["review"]
        for name, sha in (heads or {}).items():
            if name not in latest["heads"] or not same_sha(latest["heads"][name], sha):
                reasons.append(f"{name}: the review covers {latest['heads'].get(name)}, the current head is {sha}.")
        scores = dict(review["scores"].get("scopes") or {}, combined=review["scores"]["combined"])
        for name, score in scores.items():
            if score < threshold:
                reasons.append(f"Safe To Merge for {name} is {score}/10, below {threshold}.")
        verdicts = {v["id"]: v["verdict"] for v in review["criteria"]}
        for criterion in state["criteria"]:
            verdict = verdicts.get(criterion["id"], "unverified")
            if verdict != "met" and not criterion["waived"]:
                reasons.append(f"{criterion['id']} is {verdict}: {criterion['text']}")
    for finding in state["findings"].values():
        if finding["state"] not in CLOSED and finding["severity"] in BLOCKING:
            reasons.append(f"{finding['id']} ({finding['severity']}) is {finding['state']}: {finding['title']}")
        if finding["state"] not in CLOSED and finding["disputes"] >= 2:
            escalation.append(f"{finding['id']} was disputed and upheld {finding['disputes']} times.")
    if state["visual"] is None:
        reasons.append("Visual impact is undecided: run `state.py set --visual yes|no`.")
    elif state["visual"] and not any(e["kind"] == "screenshot" for e in state["evidence"]):
        reasons.append("The change is visual but no screenshot is recorded.")
    passed = not reasons
    if not passed:
        if len(reviewed) >= state["maxRounds"]:
            escalation.append(f"{len(reviewed)} review rounds are complete; the limit is {state['maxRounds']}.")
        combined = [r["review"]["scores"]["combined"] for r in reviewed]
        if len(combined) >= 3 and combined[-1] <= combined[-2] <= combined[-3]:
            escalation.append(f"The combined score did not improve for two rounds: {combined[-3:]}.")
    else:
        escalation = []
    return {"pass": passed, "escalate": bool(escalation), "round": latest["n"] if latest else 0,
            "reasons": reasons, "escalation": escalation}


def cmd_gate(args):
    state = load(args.run)
    result = gate(state, parse_heads(args.head))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 3 if result["escalate"] else 1


def cmd_status(args):
    state = load(args.run)
    latest = state["rounds"][-1] if state["rounds"] else None
    print(json.dumps({
        "run": args.run, "repo": state["repo"], "ticket": state.get("ticket"), "publish": state["publish"],
        "roles": state.get("roles"), "visual": state["visual"],
        "criteria": [{"id": c["id"], "text": c["text"], "waived": c["waived"]} for c in state["criteria"]],
        "round": latest and {"n": latest["n"], "heads": latest["heads"], "attempts": latest["attempts"],
                             "reviewed": bool(latest.get("review"))},
        "scores": [r["review"]["scores"] for r in state["rounds"] if r.get("review")],
        "openFindings": [{k: f[k] for k in ("id", "severity", "state", "title", "disputes")}
                         for f in state["findings"].values() if f["state"] not in CLOSED],
        "implementation": (state.get("implementation") or [None])[-1],
        "evidence": [e["path"] for e in state["evidence"]],
        "pullRequests": state["pullRequests"], "gate": gate(state),
    }, ensure_ascii=False, indent=2))


def cmd_report(args):
    state = load(args.run)
    reviewed = [r for r in state["rounds"] if r.get("review")]
    lines = [f"Completed independent reviews: **{len(reviewed)}**.", "",
             "| Round | Reviewer | Reviewed commit | Safe To Merge | CI | Findings |",
             "| --- | --- | --- | --- | --- | --- |"]
    for entry in reviewed:
        review = entry["review"]
        heads = ", ".join(f"{name} `{sha[:9]}`" if len(entry["heads"]) > 1 else f"`{sha[:9]}`"
                          for name, sha in entry["heads"].items())
        scopes = review["scores"].get("scopes") or {}
        scores = ", ".join([f"{name} {score}/10" for name, score in scopes.items()]
                           + [f"{'combined ' if scopes else ''}{review['scores']['combined']}/10"])
        lines.append(f"| {entry['n']} | {review.get('model') or 'unrecorded'} | {heads} | {scores} | {review['ci']} | "
                     f"{', '.join(review['findings']) or 'none'} |")
    failed = sum(1 for r in state["rounds"] for a in r["attempts"] if a.get("outcome") in ("failed", "cancelled"))
    if failed:
        lines += ["", f"Failed or cancelled review attempts, not scored: {failed}."]
    lines += ["", "### Findings", ""]
    if not state["findings"]:
        lines.append("No security or correctness defects were found. No review-driven repairs were needed.")
    for finding in state["findings"].values():
        trail = "; ".join(f"round {h['round']} {h['by']}: {h['state']}" + (f" ({h['commit'][:9]})" if h.get("commit") else "")
                          for h in finding["history"])
        lines.append(f"- **{finding['id']}** ({finding['severity']}, {finding['state']}) {finding['title']} — "
                     f"`{finding['file']}`. Impact: {finding['impact']} History: {trail}.")
    if state["criteria"]:
        verdicts = {v["id"]: v for v in reviewed[-1]["review"]["criteria"]} if reviewed else {}
        lines += ["", "### Acceptance criteria", "", "| ID | Criterion | Verdict | Evidence |", "| --- | --- | --- | --- |"]
        for criterion in state["criteria"]:
            verdict = verdicts.get(criterion["id"], {})
            shown = f"waived: {criterion['waived']}" if criterion["waived"] else verdict.get("verdict", "unverified")
            evidence = str(verdict.get("evidence", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {criterion['id']} | {criterion['text'].replace('|', chr(92) + '|')} | {shown} | {evidence} |")
    if state["evidence"]:
        lines += ["", "### Evidence files", ""]
        lines += [f"- {e['label']} ({e['kind']}{', ' + e['criterion'] if e.get('criterion') else ''}): `{os.path.basename(e['path'])}`"
                  for e in state["evidence"]]
    print("\n".join(lines))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)

    def command(name, handler, summary, run=True):
        sub = commands.add_parser(name, help=summary, description=summary)
        sub.set_defaults(handler=handler)
        if run:
            sub.add_argument("--run", required=True, help="Run directory printed by `init`")
        return sub

    sub = command("init", cmd_init, "Create a run directory and its state file", run=False)
    sub.add_argument("--repo", required=True)
    sub.add_argument("--task")
    sub.add_argument("--task-file")
    sub.add_argument("--ticket")
    sub.add_argument("--publish", choices=("after-gate", "existing-pr", "never"), default="after-gate")
    sub.add_argument("--roles", help="JSON file printed by select_roles.py")
    sub.add_argument("--max-rounds", type=int, default=5)
    sub.add_argument("--threshold", type=int, default=9)

    sub = command("list", cmd_list, "List the runs recorded for a repository", run=False)
    sub.add_argument("--repo", required=True)

    sub = command("criteria", cmd_criteria, "Record acceptance criteria and give them stable IDs")
    sub.add_argument("--issue-json", help="Output of `gh issue view N --json number,title,body,url`")
    sub.add_argument("--add", action="append", help="One more criterion, such as a coverage requirement")

    sub = command("round", cmd_round, "Start a review round on a commit")
    sub.add_argument("--head", action="append", required=True, help="SHA, or scope=SHA once per repository")
    sub.add_argument("--base")
    sub.add_argument("--replace", action="store_true", help="Restart an unreviewed round on a new head")

    sub = command("attempt", cmd_attempt, "Record a review launch and its outcome")
    sub.add_argument("--client-request-id", required=True)
    sub.add_argument("--task-id")
    sub.add_argument("--model")
    sub.add_argument("--outcome", choices=("launched", "completed", "failed", "cancelled"), default="launched")

    sub = command("review", cmd_review, "Validate and record the reviewer's answer for the current round")
    sub.add_argument("--file", required=True, help="File holding the reviewer's full answer, or -")
    sub.add_argument("--task-id")
    sub.add_argument("--model")
    sub.add_argument("--replace", action="store_true")

    sub = command("impl", cmd_impl, "Validate and record the implementer's report")
    sub.add_argument("--file", required=True, help="File holding the implementer's full answer, or -")
    sub.add_argument("--task-id")
    sub.add_argument("--thread-id")
    sub.add_argument("--model")

    sub = command("finding", cmd_finding, "Record a repair, a dispute or a user waiver of a finding")
    sub.add_argument("--id", required=True)
    sub.add_argument("--action", required=True, choices=("fixed", "disputed", "waived"))
    sub.add_argument("--note")
    sub.add_argument("--commit")
    sub.add_argument("--by", default="implementer")

    sub = command("waive", cmd_waive, "Record that the user waived an acceptance criterion")
    sub.add_argument("--criterion", required=True)
    sub.add_argument("--reason", required=True)

    sub = command("evidence", cmd_evidence, "Copy a screenshot, recording or log into the run")
    sub.add_argument("--path", required=True)
    sub.add_argument("--label")
    sub.add_argument("--kind", choices=("screenshot", "recording", "log"), default="screenshot")
    sub.add_argument("--criterion")

    sub = command("set", cmd_set, "Change run settings or record a pull request")
    sub.add_argument("--visual", choices=("yes", "no"))
    sub.add_argument("--max-rounds", type=int)
    sub.add_argument("--threshold", type=int)
    sub.add_argument("--pull-request")
    sub.add_argument("--note")
    sub.add_argument("--finished", choices=("passed", "blocked", "stopped"))

    sub = command("gate", cmd_gate, "Exit 0 when the gate passes, 1 to continue, 3 to ask the user")
    sub.add_argument("--head", action="append", required=True, help="Current SHA, or scope=SHA per repository")

    command("status", cmd_status, "Print what is needed to resume the loop")
    command("report", cmd_report, "Print the review history as Markdown")

    args = parser.parse_args(argv)
    try:
        return args.handler(args) or 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"state.py {args.command} blocked: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
