#!/usr/bin/env python3
"""Resolve the implementer and reviewer of a T3 review loop from the live catalog.

Roles come from arguments, then the user's config, then family defaults. No model
ID is written here: defaults are name patterns ("opus", "sol", "grok") resolved to
the newest matching model that the catalog advertises right now.
"""

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


class Blocked(ValueError):
    pass


def unwrap(payload):
    """Accept the capabilities object or an MCP result wrapping it."""
    if not isinstance(payload, dict):
        raise Blocked("Expected a capabilities JSON object.")
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
    raise Blocked("Payload does not contain orchestrator_capabilities data.")


def load_json(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as source:
        return json.load(source)


def merge_catalogs(payloads):
    """Merge a catalog with later `search` results: models are unioned per instance."""
    catalogs = [unwrap(p) for p in payloads]
    base = json.loads(json.dumps(catalogs[0]))
    providers = base.get("providers")
    if not isinstance(providers, list) or any(not isinstance(p, dict) for p in providers):
        raise Blocked("Invalid provider catalog.")
    by_id = {p.get("providerInstanceId"): p for p in providers}
    for extra in catalogs[1:]:
        for provider in extra.get("providers") or []:
            if not isinstance(provider, dict):
                continue
            known = by_id.get(provider.get("providerInstanceId"))
            if known is None:
                providers.append(provider)
                by_id[provider.get("providerInstanceId")] = provider
                continue
            seen = {m.get("id") for m in models_of(known)}
            known.setdefault("models", [])
            for model in models_of(provider):
                if model["id"] not in seen:
                    known["models"].append(model)
                    seen.add(model["id"])
    return base


def models_of(provider):
    models = provider.get("models")
    if not isinstance(models, list):
        return []
    return [m for m in models if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"]]


def norm(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def version_of(model_id):
    return tuple(int(n) for n in re.findall(r"\d+", model_id))


def vendor_of(model_id):
    match = re.match(r"[a-z]+", norm(model_id))
    return match.group(0) if match else ""


def ineligible_reason(provider, lead):
    """Return None when `provider` can run a child task for this lead."""
    reasons = []
    if not provider.get("providerInstanceId"):
        reasons.append("no provider instance id")
    if provider.get("canRunChildTask") is not True:
        reasons.append("cannot run child tasks")
    if not models_of(provider):
        reasons.append("advertises no models")
    if provider.get("providerInstanceId") != lead.get("providerInstanceId"):
        if lead.get("canRunCrossProviderChildTask") is not True:
            reasons.append("the lead cannot delegate across providers")
        if provider.get("canRunCrossProviderChildTask") is not True:
            reasons.append("does not accept cross-provider child tasks")
    if not reasons:
        return None
    constraints = [c for c in provider.get("constraints") or [] if isinstance(c, str)]
    return "; ".join(reasons + constraints)


def resolve_model(provider, pattern):
    """Newest advertised model matching `pattern`; exact ID and version suffix win."""
    models = models_of(provider)
    wanted = norm(pattern)
    for model in models:
        if norm(model["id"]) == wanted:
            return model
    matches = [m for m in models
               if f"-{wanted}-" in f"-{norm(m['id'])}-" or f"-{wanted}-" in f"-{norm(m.get('label', ''))}-"]
    if re.search(r"\d", wanted):
        suffix = [m for m in matches if norm(m["id"]).endswith(wanted)]
        matches = suffix or matches
    if not matches:
        hint = ""
        if provider.get("omittedModels"):
            hint = (f" The catalog omits {provider['omittedModels']} models: call orchestrator_capabilities "
                    f"with search={pattern!r} and pass that result as an extra catalog file.")
        raise Blocked(f"{provider.get('providerInstanceId')!r} advertises no model matching {pattern!r}. "
                      f"Advertised: {', '.join(m['id'] for m in models) or 'none'}.{hint}")
    matches.sort(key=lambda m: version_of(m["id"]), reverse=True)
    if len(matches) > 1 and version_of(matches[0]["id"]) == version_of(matches[1]["id"]):
        tied = [m["id"] for m in matches if version_of(m["id"]) == version_of(matches[0]["id"])]
        raise Blocked(f"{pattern!r} is ambiguous on {provider.get('providerInstanceId')!r}: {', '.join(tied)}.")
    return matches[0]


def effort_options(model, effort, defaults, *, explicit, notes, role):
    if not effort:
        return {}
    for option in model.get("options") or []:
        if not isinstance(option, dict) or option.get("id") not in defaults["effortOptionIds"]:
            continue
        values = option.get("values") or []
        if effort in values:
            return {option["id"]: effort}
        if explicit:
            raise Blocked(f"{model['id']} does not offer effort {effort!r}. Offered: {', '.join(map(str, values))}.")
        notes.append(f"{role}: {model['id']} does not offer effort {effort!r}; its own default applies.")
        return {}
    if explicit:
        raise Blocked(f"{model['id']} has no effort option.")
    notes.append(f"{role}: {model['id']} has no effort option; none was set.")
    return {}


def find_providers(token, providers, defaults):
    """Providers named by an instance ID, a driver kind or an alias; [] if none."""
    by_instance = [p for p in providers if p.get("providerInstanceId") == token]
    if by_instance:
        return by_instance
    driver = defaults["aliases"].get(token.lower(), token)
    return [p for p in providers if str(p.get("driverKind", "")).lower() == driver.lower()]


def ordered(providers, defaults, lead):
    order = defaults["order"]

    def rank(provider):
        driver = provider.get("driverKind")
        return (order.index(driver) if driver in order else len(order),
                provider.get("providerInstanceId") != lead.get("providerInstanceId"))
    return sorted(providers, key=rank)


def delegate(provider, model, options, source):
    target = {"providerInstanceId": provider["providerInstanceId"], "model": model["id"]}
    if options:
        target["options"] = options
    return {
        "kind": "delegate",
        "target": target,
        "driverKind": provider.get("driverKind"),
        "label": model.get("label") or model["id"],
        "vendor": vendor_of(model["id"]),
        "source": source,
    }


def resolve_spec(spec, role, catalog, lead, defaults, source, notes):
    spec = spec.strip()
    if spec.lower() == "lead":
        return {"kind": "lead", "source": source}
    body, _, effort = spec.partition("@")
    provider_token, _, pattern = body.partition(":")
    providers = catalog["providers"]
    named = find_providers(provider_token, providers, defaults)
    if not named and pattern:
        raise Blocked(f"{role}: no provider instance, driver or alias named {provider_token!r} in the catalog.")
    # A bare token names a provider first; failing that, it is a model pattern on any provider.
    attempts = [(named, pattern)] if named else []
    if not pattern:
        attempts.append((providers, provider_token))
    failures = []
    for group, wanted_pattern in attempts:
        for provider in ordered(group, defaults, lead):
            reason = ineligible_reason(provider, lead)
            if reason:
                failures.append(f"{provider.get('providerInstanceId')}: {reason}")
                continue
            family = defaults["drivers"].get(provider.get("driverKind"), {})
            wanted = wanted_pattern or family.get("model")
            if not wanted:
                failures.append(f"{provider.get('providerInstanceId')}: no default model for driver "
                                f"{provider.get('driverKind')!r}; name one as {provider_token}:<model>")
                continue
            try:
                model = resolve_model(provider, wanted)
            except Blocked as error:
                failures.append(str(error))
                continue
            options = effort_options(model, effort or family.get("effort"), defaults,
                                     explicit=bool(effort), notes=notes, role=role)
            return delegate(provider, model, options, source)
    failures = list(dict.fromkeys(failures))
    raise Blocked(f"{role}: nothing in the catalog can serve {spec!r}. " + " | ".join(failures))


def default_candidates(catalog, lead, defaults, notes):
    found = []
    for provider in ordered(catalog["providers"], defaults, lead):
        family = defaults["drivers"].get(provider.get("driverKind"))
        if not family or ineligible_reason(provider, lead):
            continue
        try:
            model = resolve_model(provider, family["model"])
        except Blocked as error:
            notes.append(f"default skipped: {error}")
            continue
        options = effort_options(model, family.get("effort"), defaults,
                                 explicit=False, notes=notes, role=provider["providerInstanceId"])
        found.append(delegate(provider, model, options, "default"))
    return found


def identity(role, lead):
    if role["kind"] == "lead":
        return vendor_of(lead["model"] or ""), lead["model"]
    return role["vendor"], role["target"]["model"]


def pick_other(candidates, counterpart, lead):
    """Prefer another vendor, then another model, then a separate task on the same model."""
    vendor, model = identity(counterpart, lead)
    for test in (lambda c: c["vendor"] != vendor, lambda c: c["target"]["model"] != model, lambda c: True):
        for candidate in candidates:
            if test(candidate):
                return candidate
    return None


def select_roles(payloads, *, implementer=None, reviewer=None, config=None, project=None, defaults=None):
    defaults = defaults or load_json(os.path.join(HERE, "defaults.json"))
    catalog = merge_catalogs(payloads)
    lead_id = catalog.get("inheritedProviderInstanceId")
    lead_provider = next((p for p in catalog["providers"] if p.get("providerInstanceId") == lead_id), None)
    if not lead_id or lead_provider is None:
        raise Blocked("The lead's provider instance is absent from the catalog.")
    lead = dict(lead_provider, model=catalog.get("inheritedModel"))

    config = config or {}
    scoped = (config.get("projects") or {}).get(project, {}) if project else {}
    specs = {}
    for role, argument in (("implementer", implementer), ("reviewer", reviewer)):
        if argument:
            specs[role] = (argument, "argument")
        elif scoped.get(role):
            specs[role] = (scoped[role], "project-config")
        elif config.get(role):
            specs[role] = (config[role], "config")

    notes = []
    roles = {role: resolve_spec(spec, role, catalog, lead, defaults, source, notes)
             for role, (spec, source) in specs.items()}
    if roles.get("implementer", {}).get("kind") == "lead" and roles.get("reviewer", {}).get("kind") == "lead":
        raise Blocked("The implementer and the reviewer must be separate tasks; both cannot be the lead.")

    if len(roles) < 2:
        candidates = default_candidates(catalog, lead, defaults, notes)
        if not candidates:
            raise Blocked("No provider in the catalog can run a delegated task with a default model. "
                          "Name the roles explicitly or enable a provider.")
        if "implementer" not in roles:
            if "reviewer" in roles and roles["reviewer"]["kind"] == "delegate":
                roles["implementer"] = pick_other(candidates, roles["reviewer"], lead)
            else:
                own = [c for c in candidates if c["target"]["providerInstanceId"] == lead_id]
                roles["implementer"] = (own or candidates)[0]
        if "reviewer" not in roles:
            roles["reviewer"] = pick_other(candidates, roles["implementer"], lead)

    first, second = identity(roles["implementer"], lead), identity(roles["reviewer"], lead)
    if first[0] != second[0]:
        independence = "cross-vendor"
    elif first[1] != second[1]:
        independence = "cross-model"
    else:
        independence = "same-model"
        notes.append("Implementer and reviewer run the same model as separate tasks; report this to the user.")
    if roles["implementer"]["kind"] == "lead":
        mode = "lead-implements"
    elif roles["reviewer"]["kind"] == "lead":
        mode = "lead-reviews"
    else:
        mode = "coordinator"
    return {
        "lead": {"providerInstanceId": lead_id, "driverKind": lead.get("driverKind"), "model": lead["model"]},
        "mode": mode,
        "implementer": roles["implementer"],
        "reviewer": roles["reviewer"],
        "independence": independence,
        "needsConfirmation": any(r["source"] == "default" for r in roles.values()),
        "notes": notes,
    }


def spec_of(role, given):
    if given:
        return given
    if role["kind"] == "lead":
        return "lead"
    return role["driverKind"] or role["target"]["providerInstanceId"]


def describe(catalog_payloads):
    catalog = merge_catalogs(catalog_payloads)
    lead = next((p for p in catalog["providers"]
                 if p.get("providerInstanceId") == catalog.get("inheritedProviderInstanceId")), {})
    usable, unusable = [], []
    for provider in catalog["providers"]:
        reason = ineligible_reason(provider, lead)
        if reason:
            unusable.append({"providerInstanceId": provider.get("providerInstanceId"), "reason": reason})
            continue
        usable.append({
            "providerInstanceId": provider["providerInstanceId"],
            "driverKind": provider.get("driverKind"),
            "models": [m["id"] for m in models_of(provider)],
            "omittedModels": provider.get("omittedModels", 0),
        })
    return {"lead": {"providerInstanceId": lead.get("providerInstanceId"), "model": catalog.get("inheritedModel")},
            "usable": usable, "unusable": unusable}


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "t3-review-loop", "config.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("catalog", nargs="+", help="Capabilities JSON file(s), or - for stdin; later files add searched models")
    parser.add_argument("--implementer", help="lead | <provider>[:<model>][@<effort>] | <model>[@<effort>]")
    parser.add_argument("--reviewer", help="Same syntax as --implementer")
    parser.add_argument("--config", default=config_path(), help="User config file (default: %(default)s)")
    parser.add_argument("--project", help="Repository path whose config entry overrides the global roles")
    parser.add_argument("--save", action="store_true", help="Remember the chosen roles in the config")
    parser.add_argument("--list", action="store_true", help="Print the usable providers and models, then exit")
    args = parser.parse_args(argv)
    try:
        payloads = [load_json(path) for path in args.catalog]
        if args.list:
            print(json.dumps(describe(payloads), ensure_ascii=False, indent=2))
            return 0
        config = load_json(args.config) if os.path.exists(args.config) else {}
        result = select_roles(payloads, implementer=args.implementer, reviewer=args.reviewer,
                              config=config, project=args.project)
        if args.save:
            holder = config.setdefault("projects", {}).setdefault(args.project, {}) if args.project else config
            holder["implementer"] = spec_of(result["implementer"], args.implementer)
            holder["reviewer"] = spec_of(result["reviewer"], args.reviewer)
            os.makedirs(os.path.dirname(args.config), exist_ok=True)
            with open(args.config, "w", encoding="utf-8") as sink:
                json.dump(config, sink, ensure_ascii=False, indent=2)
                sink.write("\n")
            result["saved"] = args.config
    except (OSError, ValueError, TypeError) as error:
        print(f"Role selection blocked: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
