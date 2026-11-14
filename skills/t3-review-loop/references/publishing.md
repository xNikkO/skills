# Publishing

Only the lead publishes, and the lead never merges anything: every PR stays open for the user. Publish the exact commit the reviewer passed: run `state.py gate --head <sha>` immediately before pushing, and stop if it does not exit `0`.

Before pushing, read the messages of the commits you are about to publish (`git log --format=%B <base>..<sha>`). If any names a model or an AI tool as author or co-author, have the implementer reword it in its worktree; the commit changes, so run a new review round. Write no such line in PR titles, descriptions or comments either.

## Conflict check before pushing

```bash
python3 <skill-dir>/scripts/conflicts.py --repo <repo> --base <base branch> --head <sha>
```

It exits `1` when the commit conflicts with the base or with an open PR, and lists the files. It merges nothing.

- **Conflict with the base:** the base moved. Have the implementer rebase in its worktree; the commit changes, so run a new review round before publishing.
- **Conflict with another open PR**, including one from an earlier ticket of this run: publish anyway, since each PR is correct against the base on its own. Name the other PR and the files in the PR description and in your account to the user, and say that whichever merges second will need a rebase. Do not merge or rebase onto the other PR to make the conflict go away.
- `sharedFiles` without a conflict needs one line in the PR description, nothing more.

## `publish=after-gate`: open a new PR

1. **Branch.** Name the branch by the repository's convention, or `<type>/<ticket>-<short-slug>`. The reviewed commit lives in the shared object store, so push it without checking it out: `git push origin <sha>:refs/heads/<branch>`.
2. **Screenshots.** If the run has screenshots, publish them:
   ```bash
   python3 <skill-dir>/scripts/publish_evidence.py --repo <repo> --name <run-id> <run>/evidence/*.png
   ```
   It commits the images to a side ref, `refs/t3-review-loop/evidence/<run-id>`, that no branch contains, pushes it, and prints Markdown image links pinned to that commit. The PR branch and the working tree are untouched. If the push is refused or the host is not GitHub, say in the PR that screenshots were shown in the T3 Code thread, and list their names.
3. **Description.** Write the body to a file from the template below and create the PR with `gh pr create --base <base> --head <branch> --title … --body-file …`.
4. **Record.** Call `link_pull_request` for the PR at once, check that its head is the reviewed SHA, and run `state.py set --pull-request <url>`. Inspect an uncertain push or creation before retrying, to avoid a duplicate PR.

Do not tick checkboxes in the ticket or close it by hand: the PR carries `Closes #N` and the verdict table. Do it only when the user asks.

```markdown
[What the change does and the resulting behavior, in two or three sentences.]

Closes #[N]

## Screenshots

| Before | After |
| --- | --- |
| [image link or "new screen"] | [image link] |

## How it was tested

- [Walkthrough in the running app: what was clicked or requested, and the result.]
- [Commands run with results and figures, such as coverage 84% on changed modules.]
- [What could not be verified, and why.]

## Review before publication

Implementer: [model]. Reviewer: [model] ([cross-vendor | cross-model | same-model]).
Final Safe To Merge: **[X]/10** at `[sha]`. CI: [not run before PR creation | pending | passed | failed].
[Only if the conflict check found something: Conflicts with #[PR] in `[files]`; whichever merges second needs a rebase.]

[Output of `state.py report`: rounds, findings, acceptance criteria.]

The score is the reviewer's assessment of the code and is separate from CI. Required checks must still pass before merging. This PR is left open for a merge decision.
```

Leave out the Screenshots section when the change is not visual. Keep every round and every original score; never replace earlier scores with the final one.

## `publish=existing-pr`: repair a published PR

- **Scope.** Record the PR URL, base and head. Pass `--skip-pr <number>` to `conflicts.py` so the PR is not compared with itself. With several PRs or repositories, start the round with one `--head <scope>=<sha>` each; the reviewer then scores each scope and the combination.
- **Review first.** Round 1 reviews the current PR head; there is no implementation step.
- **Repairs.** The implementer starts from the PR head in its worktree and commits there. Push with `git push origin <sha>:refs/heads/<pr-branch>`. It must be a fast-forward; if it is not, rebase in the implementer's worktree, which changes the commit and needs a new round.
- **Round comments.** After each recorded review, post one comment on each scoped PR: reviewer model, round, reviewed SHA, open findings or their absence, criteria verdicts, checks and limits, `Safe To Merge: X/10`, `CI: …`. Put a finding on its line where the host supports it. Use an ordinary comment or a COMMENT review, never APPROVE or REQUEST_CHANGES.
- **Account.** Post as the account that published the PR: take the login from the PR's author metadata, not from commit authors or local git configuration, and check the authenticated login before every comment. If that account is not available, keep working locally and report the posting blocker. Never post as another account and never ask for credentials in chat.
- **Finish.** Update the PR description with the screenshots and the `state.py report` history when the gate passes. Confirm `list_thread_pull_requests`, link anything missing, and unwatch the PRs unless the user asked for monitoring.

## `publish=never`

Stop after the gate with the passing commit, the prepared PR body file and the screenshots. Say that nothing was pushed.

## CI

- Report `Safe To Merge` and `CI` as two fields. Pending CI does not lower the score, make it conditional, or start another round.
- After publication, check CI once. If the user asked for monitoring, use T3 `watch_pull_request` and yield; do not poll.
- A completed failure caused by the code is a defect: repair it, run a new round, and push only after the gate passes again. Add that round to the PR description as a post-publication round. An infrastructure or credential failure is reported as such, not as a code defect.
- A passing CI update alone needs no new review.
