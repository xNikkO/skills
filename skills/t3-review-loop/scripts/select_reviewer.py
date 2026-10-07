#!/usr/bin/env python3
"""Choose the opposite-provider T3 reviewer from live capabilities JSON."""

import argparse
import json
import sys


DEFAULTS = {
    "codex": ("claudeAgent", "claude-opus-5-5"),
    "claudeAgent": ("codex", "gpt-6.1-sol"),
}


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


def select_reviewer(payload, *, model=None, provider_instance=None):
    catalog = unwrap(payload)
    providers = catalog.get("providers")
    if not isinstance(providers, list) or any(not isinstance(p, dict) for p in providers):
        raise ValueError("Invalid provider catalog.")
    caller_id = catalog.get("inheritedProviderInstanceId")
    caller = next((p for p in providers if p.get("providerInstanceId") == caller_id), None)
    if not caller_id or not caller:
        raise ValueError("Current implementer provider is absent from the catalog.")
    driver = caller.get("driverKind")
    if driver not in DEFAULTS:
        raise ValueError(f"No requested reviewer policy for implementer driver {driver!r}.")
    if caller.get("canRunCrossProviderChildTask") is not True:
        raise ValueError("Current implementer cannot delegate across providers.")
    target_driver, default_model = DEFAULTS[driver]
    requested_model = model or default_model
    for provider in providers:
        if provider.get("driverKind") != target_driver:
            continue
        if provider_instance and provider.get("providerInstanceId") != provider_instance:
            continue
        if provider.get("canRunChildTask") is not True:
            continue
        if provider.get("canRunCrossProviderChildTask") is not True:
            continue
        if not provider.get("providerInstanceId"):
            continue
        available = provider.get("models") or []
        if not isinstance(available, list):
            continue
        if not any(isinstance(m, dict) and m.get("id") == requested_model for m in available):
            continue
        return {
            "implementerProviderInstanceId": caller_id,
            "implementerDriverKind": driver,
            "target": {"providerInstanceId": provider["providerInstanceId"], "model": requested_model},
        }
    restriction = f" on {provider_instance!r}" if provider_instance else ""
    raise ValueError(
        f"No enabled {target_driver} provider{restriction} can review with {requested_model!r}. "
        "Do not substitute a different model or perform self-review."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", help="Capabilities JSON file, or - for stdin")
    parser.add_argument("--model", help="Explicit user override within the opposite provider family")
    parser.add_argument("--provider-instance", help="Explicit user choice from the live catalog")
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
