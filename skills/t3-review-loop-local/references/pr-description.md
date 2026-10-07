# PR description after the local gate

Adapt language and length to the project. Fill with the actual history; preserve all impactful findings and unresolved limitations. Never create this PR before the local passing result.

```markdown
[Problem, concrete implementation, resulting behavior.]

## Pre-publication T3 Code review

Completed independent reviews before opening this PR: **[N]**.
[For multiple repositories: total task count plus how many rounds actually covered this PR. One task covering multiple repositories counts once overall.]

| Round | Reviewer/model and routing | Reviewed commit/tree and coverage | Score for this change / combined | Findings and subsequent repair or evidence |
| --- | --- | --- | --- | --- |
| [1] | [actual model; cross-family or single-family fallback reason] | [identity and repositories] | [original scores] | [finding IDs, fixes or verification] |

Findings discovered before publication:
- [Stable ID, severity, reachable impact, correction, regression evidence, resolving round/commit.]
- [Disputed/rejected finding and evidence; do not label as a code repair.]
[If none: No confirmed security or correctness defects were found. No review-driven repairs were needed.]

Final LOCAL Safe To Merge: **[X/10 for this change; Y/10 combined]**.
Passing reviewed artifact: [base, local commit/tree and dependencies].
Published head: [commit/tree; matches the passing artifact].

## Validation

- [Actual local commands/results and artifact they cover.]
- [Essential limitations, dependency/rollout order if relevant.]
- Remote CI: [not run before PR creation; pending or actual observed outcome]. CI status is separate from Safe To Merge; absent/queued/running CI does not lower or condition the score. The local score does not claim remote CI passed. Required remote checks remain a merge prerequisite.

[Optional, only if applicable: Post-publication review rounds, fixes and scores, clearly separate from the original N pre-publication rounds.]

PR remains open for the user's merge decision; no automatic merge.
```

Failed/cancelled task attempts have no score and are separate from completed reviews. Do not count idempotent launch retries, copied summaries, or a promised reviewer as completed reviews. Use a structured host tool argument or a real body file for multiline text; use `--body-file` with `gh`.
