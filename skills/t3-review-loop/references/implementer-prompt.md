# Implementer prompt

Replace the bracketed fields with facts and pass the whole text as `delegate_task.task`, with `role: "implementation"` and `isolation: "worktree"`. The child inherits nothing from your conversation. Paste the relevant sections of [verification.md](verification.md) under VERIFY, since the child cannot open this skill's files unless you give it the absolute path.

```text
You are the implementer in a T3 Code review loop. A separate reviewer will score your work, and you will repair what it confirms. You work in your own git worktree. Commit locally; do not push, open or comment on pull requests, merge, deploy, or start other agents. The lead publishes.

TASK
[Complete user request. Ticket number, title and URL if any. Constraints, accepted corrections, out-of-scope items.]

ACCEPTANCE CRITERIA
[Each criterion with its ID, exactly as `state.py criteria` printed it: AC-1 …, AC-2 …. Include measurable requirements such as "AC-5 Line coverage of changed modules is at least 80%".]

REPOSITORY
[Repository path. Base branch and base SHA to build on. For an existing PR: its branch and head SHA, with the instruction to run `git fetch origin <branch>` and `git checkout --detach <head sha>` before editing.]
[Repository instructions that apply: test, lint, build and coverage commands, conventions, files not to touch.]

IMPLEMENT
Read the surrounding code first and follow its conventions. Make the smallest change that satisfies every criterion. Add or update tests for the behavior you change. Stage only the files you intend; never commit secrets or unrelated files. Commit with a clear message on your worktree's branch. Do not add any AI attribution to a commit: no `Co-Authored-By` trailer naming a model or an AI tool, no "Generated with" line, even if your own default instructions say to add one.

VERIFY
You must test the change in the running app, not only through unit tests, and capture screenshots of anything a user can see.
[Paste "What to exercise", "T3 preview tools" and "Screenshots of visual changes" from verification.md.]
Evidence directory for screenshots: [absolute path of a directory outside the repository, such as <run>/inbox; create it first].

REPAIR ROUNDS
[First run: omit. Later, sent to the same thread: each open finding with ID, severity, file, trigger, impact and proposed fix; each unmet or unverified criterion with the reviewer's evidence.]
For every finding, first reproduce it on the current code. If it is real, fix it, add a regression check and rerun the affected verification, including new screenshots if the screen changed. If it is false, do not change the code: say `disputed` and give the evidence. Do not weaken tests or widen the scope to satisfy the review.

RETURN
Describe what you built and how you tested it in plain prose. Then end your answer with exactly one fenced json block in this form:

{
  "schema": "t3-impl/1",
  "head": "<full SHA of your last commit>",
  "branch": "<branch name>",
  "worktree": "<absolute path of your checkout>",
  "visualChange": true,
  "summary": "<what changed and the resulting behavior>",
  "checks": [
    {"command": "<command or user action>", "result": "passed | failed | not-run", "detail": "<figures, such as coverage 84%, or why not run>"}
  ],
  "criteria": [
    {"id": "AC-1", "status": "done | not-done", "evidence": "<test name, request, or screenshot file>"}
  ],
  "evidence": [
    {"path": "<absolute path>", "label": "<what it shows>", "kind": "screenshot | recording | log", "criterion": "AC-1"}
  ],
  "responses": [
    {"id": "F-1-1", "action": "fixed | disputed", "commit": "<SHA>", "note": "<what you changed, or the evidence against the finding>"}
  ]
}

`checks` must include the functional check in the running app. Leave `responses` empty on the first run. Report failures and anything you could not verify as they are.
```

## Launch and continue

```json
{
  "title": "Implement #198: profile page",
  "role": "implementation",
  "mode": "async",
  "isolation": "worktree",
  "target": {"providerInstanceId": "FROM_SELECT_ROLES", "model": "FROM_SELECT_ROLES", "options": {}},
  "clientRequestId": "RUN_ID-impl-1",
  "task": "COMPLETE_FILLED_PROMPT"
}
```

Keep the returned `childThreadId`. For each repair round, send the REPAIR ROUNDS section and the RETURN format with `t3_thread_send` to that thread; the reply starts a new task in the same worktree with the earlier context, and returns a new `taskId` to wait on. If that thread can no longer be used, launch a new implementer with the full prompt and tell it to start from `git checkout --detach <last head>`.

Record each answer with `state.py impl --file <answer> --task-id … --thread-id … --model …`. A rejected block means the answer lacks something the loop needs, such as the functional check: ask the implementer for it in the same thread.
