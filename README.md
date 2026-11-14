# AI agent skills

Reusable AI agent skills for use across projects and by different users.

## Install with the skills CLI

Requirements: T3 Code with delegation tools available, Python 3, `git`, and `gh` for tickets and pull requests. Installing a skill does not install T3 Code or configure providers.

Install the skill globally for Codex and Claude Code:

```bash
npx skills add xNikkO/skills --skill t3-review-loop --agent codex claude-code --global
```

List available skills without installing them:

```bash
npx skills add xNikkO/skills --list
```

## T3 review loop

[The skill](skills/t3-review-loop/SKILL.md) takes a task through T3 Code from implementation to a pull request. The agent you launch is the **lead**: it coordinates the work and reports to you. An **implementer** writes the code and a **reviewer** scores it; they are always two separate tasks. The loop repeats review and repair until the code earns **Safe To Merge of at least 9/10**, then opens a PR with the review history. PRs are left unmerged.

### Usage

```text
$t3-review-loop ticket=198
$t3-review-loop tickets=198,195,315
$t3-review-loop Add CSV export to the report page
$t3-review-loop https://github.com/owner/repo/pull/123
$t3-review-loop implementer=cursor reviewer=claude:opus@xhigh ticket=198
```

| Option | Meaning | Default |
| --- | --- | --- |
| `implementer=`, `reviewer=` | `lead`, a provider (`claude`, `gpt`, `cursor`), a model (`opus`, `grok-4.6`), or `provider:model@effort` | saved choice, else the newest Opus, Sol or Grok at `high` |
| `ticket=<number>` | Issue to implement; its checkboxes become the acceptance criteria | none |
| `tickets=<n,n,…>` | Several issues, one after another, each on its own branch with its own PR | none |
| `publish=` | `after-gate` opens a PR once the gate passes, `existing-pr` repairs a published PR, `never` stays local | `existing-pr` for a PR URL, otherwise `after-gate` |
| `max-rounds=`, `threshold=` | Review rounds before the skill asks you; passing score | 5 and 9 |

### Roles and models

Roles are chosen at launch from the live T3 Code model catalog. The skill contains name patterns, not model IDs.

| Provider | Default model | Effort |
| --- | --- | --- |
| Claude | newest Opus | high |
| Codex (GPT) | newest Sol | high |
| Cursor | newest Grok | high |

With no arguments, the implementer is the default model of the lead's own provider and the reviewer is the first usable model from another vendor. The lead's own model only orchestrates. On the first run the skill shows its proposal and asks once; it saves the choice in `~/.config/t3-review-loop/config.json`, globally or for one repository.

The one hard rule: the implementer and the reviewer are separate tasks. Another vendor is preferred, not required. An unavailable provider or model is reported as a blocker with its reason; the skill does not substitute a model silently.

### What the loop does

0. Before any work it checks for conflicts: whether the local base branch is current and whether open PRs already conflict with it, and tells you at once. Before opening a PR it checks the finished commit against the base and every open PR.
1. It reads the ticket and gives its checkboxes stable IDs (`AC-1`, `AC-2`…). Measurable requirements, such as 80% coverage, are added as further criteria.
2. The implementer writes the code in its own worktree, runs the tests and **checks the change in the running app**: in the T3 Code browser, with requests to the API, or in whatever way fits the change.
3. For a change a user can see, the implementer takes **screenshots** (before and after). They appear in the final account in the T3 Code thread and in the PR description.
4. The reviewer, in a fresh task, scores the code and gives each criterion a verdict: met, unmet or unverified, with evidence.
5. The implementer repairs confirmed findings or disputes wrong ones with evidence. The round repeats.
6. The gate passes when the score reaches the threshold, no P0–P2 finding is open, every criterion is met or waived by the user, a visual change has a screenshot, and the reviewed commit is the current one.
7. The skill asks you when the round limit is reached, the score does not improve for two rounds, or the same finding was disputed and upheld twice.

**The skill never merges**: not a PR, not a branch into the base, not one ticket's branch into another's. With several tickets, each starts from the base branch and gets its own PR; conflicts between them are reported, not resolved by merging.

**10/10 is the normal result of a clean review.** The reviewer starts from 10 and takes points off only for something it can name: a finding or a missing piece of evidence. A score below 10 without a stated reason is rejected by the script.

**After each PR you get a short account**: what changed from the user's point of view, the PR link, screenshots for visual changes, and one line with the score. The full review history is in the PR description.

**Safe To Merge and CI status are reported separately.** Pending CI does not lower the score. Required checks must pass before an actual merge. Only the lead writes outside the machine (pushes, PRs, comments); in `after-gate` mode nothing leaves the machine before the gate passes.

The loop's state is kept in `~/.local/state/t3-review-loop/`, outside the repository, so it survives context compaction and an interrupted session.

### Manual global installation

Clone the repository into a directory of your choice. Make `skills/t3-review-loop` available as a global skill in `~/.agents/skills/`. You can also create symlinks to it in the Claude skill directory (`~/.claude/skills/`) and the Codex skill directory (`$CODEX_HOME/skills/`, defaulting to `~/.codex/skills/`). Keep the name `t3-review-loop` and preserve existing skills in these directories.

T3 Code may require refreshing the skill list or starting a new thread to discover newly installed skills.

### Migrating from `t3-review-loop-local`

The local variant is now part of this skill: its behavior is the default `publish=after-gate` mode. Remove the old skill if you have it installed:

```bash
npx skills remove t3-review-loop-local --global
```

## Structure

```text
skills/t3-review-loop/
├── SKILL.md
├── agents/openai.yaml
├── references/
│   ├── roles.md                choosing roles, syntax, defaults
│   ├── implementer-prompt.md   implementer prompt and report format
│   ├── reviewer-prompt.md      reviewer prompt and result format
│   ├── verification.md         testing in the app and screenshots
│   ├── tickets.md              several tickets in one run
│   └── publishing.md           PR, comments, screenshots in the PR, CI
└── scripts/
    ├── select_roles.py         resolves roles from the T3 Code catalog
    ├── state.py                loop state, report validation, gate, history
    ├── conflicts.py            finds conflicts with the base and open PRs
    ├── publish_evidence.py     publishes screenshots for a PR
    └── defaults.json           default model patterns
tests/                          script tests: python3 -m unittest discover -s tests
```
