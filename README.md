# AI agent skills

Reusable AI agent skills for use across projects and by different users.

## Install with the skills CLI

Requirements: T3 Code with delegation tools available, Python 3, and a supported reviewer provider and model. Installing a skill does not install T3 Code or configure providers.

Install both skills globally for Codex and Claude Code:

```bash
npx skills add xNikkO/skills --skill t3-review-loop t3-review-loop-local --agent codex claude-code --global
```

Install an individual skill:

```bash
npx skills add xNikkO/skills --skill t3-review-loop
npx skills add xNikkO/skills --skill t3-review-loop-local
```

List available skills without installing them:

```bash
npx skills add xNikkO/skills --list
```

## T3 review loop

[The skill instructions](skills/t3-review-loop/SKILL.md) guide independent security and correctness reviews through T3 Code. The lead agent fixes confirmed defects, runs relevant tests, and repeats the review until every PR and the combined change earn **Safe To Merge of at least 9/10**.

| Lead agent and implementer | Reviewer |
| --- | --- |
| Codex | Claude Opus 5.5 |
| Claude | GPT-6.1-Sol |

Scores apply to the current commits. Actual blockers and missing required validation are reported without inflating the score. The skill requires T3 Code delegation tools and the specified reviewer models.

Both variants report **Safe To Merge and CI status separately**. Pending CI does not lower the score or make it conditional: sufficiently validated code can earn **9/10, CI: pending**. A passing CI update alone does not require another review. A confirmed code defect found by CI still requires repair, and required checks must pass before an actual merge.

Each completed round leaves a comment on every scoped PR under the account that published it. The agent verifies the PR author and authenticated account separately for each PR. An unavailable account is reported as a posting blocker. The skill has no hard-coded user identity and **does not merge PRs**.

The final report includes the number of completed reviews, score history for each PR and the combined change, findings, repairs between rounds, and validation results. It ends with an account of what the task implemented and what review repaired. PRs remain open and unmerged.

### Usage

```text
$t3-review-loop Review and fix PR <link>.
```

### Manual global installation

Clone the repository into a directory of your choice. Make `skills/t3-review-loop` available as a global skill in `~/.agents/skills/`. You can also create symlinks to it in the Claude skill directory (`~/.claude/skills/`) and the Codex skill directory (`$CODEX_HOME/skills/`, defaulting to `~/.codex/skills/`). Keep the name `t3-review-loop` and preserve existing skills in these directories.

T3 Code may require refreshing the skill list or starting a new thread to discover newly installed skills.

## T3 review loop local

[The local variant](skills/t3-review-loop-local/SKILL.md) keeps implementation, review, and repairs in T3 Code agent conversations. Code remains local, with no pushes or PRs, including drafts, until every scoped change and the combined feature earn **Safe To Merge of at least 9/10** and pass sufficient local validation. Only then does the agent push the exact reviewed code and open PRs.

The PR description includes the number of completed reviews before publication, score history, findings and their repairs or rebuttals, reviewed artifact identities, and test results. The absence of remote CI before PR creation does not itself block local review. After publication, required CI must still pass before merging. The skill does not merge PRs.

When both provider families are available, Codex is reviewed by Claude Opus 5.5 and Claude is reviewed by GPT-6.1-Sol. **Only when the opposite family is unavailable** does a separate agent from the available family review the change: Codex → Codex or Claude → Claude. A missing preferred model or a launch failure alone does not enable this fallback.

```text
$t3-review-loop-local Implement <task>, run local review, and open a PR only after the review gate passes.
```

Use the same installation steps with the folder and name `t3-review-loop-local`. Both skills can be installed together. Use `t3-review-loop` to review published PRs.

## Structure

```text
skills/t3-review-loop/
├── SKILL.md
├── agents/openai.yaml
├── references/reviewer-prompt.md
└── scripts/select_reviewer.py
```

The helper selects a reviewer from the live T3 Code catalog, skips unavailable providers, and does not silently substitute another model for the requested one.

The `skills/t3-review-loop-local/` variant has its own reviewer selection helper and an additional `references/pr-description.md` template for recording local review history in the eventual PR.
