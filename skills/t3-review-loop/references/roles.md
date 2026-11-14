# Roles and models

## Three ways to run

| Mode | Implementer | Reviewer | When |
| --- | --- | --- | --- |
| `coordinator` (default) | delegate | delegate | The lead keeps a small context and can run long tasks or several tickets. |
| `lead-implements` | lead | delegate | `implementer=lead`: the user wants the current model to write the code. |
| `lead-reviews` | delegate | lead | `reviewer=lead`: the lead judges the work. It has no fresh context per round, so use it only on request. |

The one hard rule: the implementer and the reviewer are separate tasks. A different vendor is preferred, a different model is second best, and the same model in a separate task is allowed. `select_roles.py` reports which of the three applies as `independence`; tell the user when it is `same-model`.

## Role syntax

```text
lead                      the agent the user launched
claude | gpt | cursor     a provider, by alias, driver kind or instance ID; its default model applies
opus | grok-4.6           a model name pattern, searched on every usable provider
cursor:opus-5@xhigh       provider, model pattern and effort
```

A pattern without a version resolves to the newest matching model in the catalog. A pattern with a version must match that version. The script never substitutes a model that the pattern does not match; an unavailable choice is a blocker with the reason, such as "Provider is not authenticated."

## Defaults

`scripts/defaults.json` holds name patterns, not model IDs:

| Provider | Default model | Effort |
| --- | --- | --- |
| Claude (`claudeAgent`) | newest `opus` | high |
| Codex (`codex`) | newest `sol` | high |
| Cursor (`cursor`) | newest `grok` | high |

With no arguments and no saved choice, the implementer is the default model of the lead's own provider and the reviewer is the first usable default from another vendor. The lead's own model is not a default for either role: the lead orchestrates.

## Order of precedence and saving

1. Arguments in the invocation.
2. The project entry in the user's config, selected by `--project <repo path>`.
3. The global entry in the config.
4. The defaults above; the result then has `needsConfirmation: true`.

The config is `~/.config/t3-review-loop/config.json` (or `$XDG_CONFIG_HOME`). `--save` writes the roles as the user gave them, or as a provider name when they came from the defaults, so "newest" keeps tracking the catalog. With `--project` it saves for that repository only.

```json
{
  "implementer": "claude",
  "reviewer": "cursor",
  "projects": {"/home/me/work/app": {"reviewer": "gpt@xhigh"}}
}
```

## Asking the user

When `needsConfirmation` is true, show the proposed implementer and reviewer with model and effort, and ask once whether to keep them. `select_roles.py <catalog> --list` prints the usable providers and models for the alternatives. Save the answer with `--save`. Do not ask when the roles came from arguments or the config.

## Models missing from the catalog

`orchestrator_capabilities` returns a short list. When a pattern is not found and the error mentions omitted models, call `orchestrator_capabilities` with `search` set to the pattern, save that result, and pass both files: `select_roles.py catalog.json search.json …`.

## Using the result

`implementer.target` and `reviewer.target` go to `delegate_task.target` unchanged, including `options`. A role with `kind: "lead"` has no target. After a launch, compare the returned `model` with the target and record the real one with `state.py attempt --model` and `state.py review --model`.
