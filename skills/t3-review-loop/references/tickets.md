# Several tickets in one run

`tickets=198,195,315` works through the issues in the order given. Each ticket is a complete loop of its own: its own run directory, its own implementer thread, its own branch from the base, its own review rounds and its own PR. The roles are chosen once and reused.

## Rules

- **One ticket, one PR.** Never put two tickets on one branch or in one PR.
- **Never merge between tickets.** The PR of a finished ticket stays open. The next ticket starts from the base branch, not from the previous ticket's branch, so that each PR can be reviewed and merged alone.
- **Finish a ticket before starting the next**: gate passed, PR opened and linked, short account given to the user. Then start the next ticket without waiting for an answer.
- Use the default `coordinator` mode. A lead that also implements will run out of context over several tickets.

## For each ticket

1. **Conflict check first.** `conflicts.py --repo <repo> --base <base>` before any work. Tell the user at once if the local base is stale or an open PR already conflicts with the base. Also read the ticket for a stated dependency on another ticket.
2. **Run the loop**, steps 2 to 6 of `SKILL.md`, with a new `state.py init --ticket <n>` and a new implementer `delegate_task`. Do not reuse the previous ticket's implementer thread or worktree.
3. **Conflict check on the result**, as [publishing.md](publishing.md) describes. Earlier tickets of this run are now open PRs, so this is where overlaps between tickets show up. Report each conflict by PR number and file.
4. **Give the short account** from step 7 of `SKILL.md`, with the PR link and screenshots.

## When a ticket cannot stand alone

If a ticket needs code that only exists in an unmerged PR, do not merge that PR and do not stack silently. Stop that ticket, tell the user which PR it depends on, and ask whether to build it on top of that PR's branch (the new PR then targets that branch and says so) or to wait. Meanwhile continue with the tickets that do not depend on it.

## When a ticket is blocked

A ticket that reaches the round limit, a stalled score or a twice-upheld dispute needs the user. Ask, record the blocker with `state.py set --finished blocked`, and move on to the next ticket instead of stopping the whole run, unless later tickets depend on it.

## At the end

Give one table: ticket, PR link, final score, rounds, CI, and a note for conflicts or blockers. Repeat that every PR is open and unmerged, and list the conflicts between them so the user can choose a merge order.
