#!/usr/bin/env python3
"""Route T3 local reviews; same-family only when the other family is unavailable."""

import argparse
import json
import sys

PREFERRED = {"codex": "gpt-6.1-sol", "claudeAgent": "claude-opus-5-5"}
OPPOSITE = {"codex": "claudeAgent", "claudeAgent": "codex"}


def unwrap(payload):
    if not isinstance(payload, dict):
        raise ValueError("Expected a capabilities JSON object.")
    if "providers" in payload:
        return payload
    structured = payload.get("structuredContent")
    if isinstance(structured, dict) and "providers" in structured:
        return structured
    for block in payload.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                parsed = json.loads(block.get("text", ""))
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, dict) and "providers" in parsed:
                return parsed
    raise ValueError("Payload does not contain orchestrator_capabilities data.")


def model_ids(provider):
    models = provider.get("models")
    if not isinstance(models, list):
        return []
    return [m["id"] for m in models if isinstance(m, dict)
            and isinstance(m.get("id"), str) and m["id"]]


def available(provider, driver):
    return (provider.get("driverKind") == driver
            and isinstance(provider.get("providerInstanceId"), str)
            and bool(provider["providerInstanceId"])
            and provider.get("canRunChildTask") is True
            and bool(model_ids(provider)))


def select_reviewer(payload, *, model=None, provider_instance=None):
    catalog = unwrap(payload)
    providers = catalog.get("providers")
    if not isinstance(providers, list) or any(not isinstance(p, dict) for p in providers):
        raise ValueError("Invalid provider catalog.")
    caller_id = catalog.get("inheritedProviderInstanceId")
    caller = next((p for p in providers if p.get("providerInstanceId") == caller_id), None)
    if not caller_id or caller is None:
        raise ValueError("Current implementer provider is absent from the catalog.")
    driver = caller.get("driverKind")
    if driver not in OPPOSITE:
        raise ValueError(f"No reviewer policy for implementer driver {driver!r}.")
    opposite = OPPOSITE[driver]
    opposite_present = any(available(p, opposite) for p in providers)
    selected_driver = opposite if opposite_present else driver
    mode = "cross-family" if opposite_present else "single-family-fallback"
    if opposite_present and caller.get("canRunCrossProviderChildTask") is not True:
        raise ValueError("Opposite family is present but cross-provider delegation is disabled; no same-family fallback.")
    if not opposite_present and caller.get("canRunChildTask") is not True:
        raise ValueError("Current implementer cannot launch a same-family child reviewer.")
    candidates = [p for p in providers if available(p, selected_driver)
                  and (not provider_instance or p["providerInstanceId"] == provider_instance)
                  and (not opposite_present or p.get("canRunCrossProviderChildTask") is True)]
    if opposite_present or model:
        choices = [model or PREFERRED[selected_driver]]
    else:
        choices = [PREFERRED[selected_driver], catalog.get("inheritedModel")]
        choices += [m for p in candidates for m in model_ids(p)]
    for requested in choices:
        if not isinstance(requested, str) or not requested:
            continue
        for provider in candidates:
            if requested in model_ids(provider):
                return {
                    "implementerProviderInstanceId": caller_id,
                    "implementerDriverKind": driver,
                    "selectionMode": mode,
                    "reason": ("Both usable families are present; use the opposite family."
                               if opposite_present else
                               f"No child-capable {opposite} instance advertises a model; use a separate {driver} child."),
                    "target": {"providerInstanceId": provider["providerInstanceId"], "model": requested},
                }
    restriction = f" on {provider_instance!r}" if provider_instance else ""
    requested = model or PREFERRED[selected_driver]
    raise ValueError(f"No eligible {selected_driver} reviewer{restriction} with model {requested!r}. "
                     "Do not bypass the family policy or perform self-review.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", help="Capabilities JSON file, or - for stdin")
    parser.add_argument("--model", help="Explicit model within the family selected by policy")
    parser.add_argument("--provider-instance", help="Explicit instance within the selected family")
    args = parser.parse_args()
    try:
        if args.catalog == "-":
            payload = json.load(sys.stdin)
        else:
            with open(args.catalog, encoding="utf-8") as source:
                payload = json.load(source)
        result = select_reviewer(payload, model=args.model, provider_instance=args.provider_instance)
    except (OSError, ValueError, TypeError) as error:
        print(f"Reviewer selection blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
