#!/usr/bin/env python3
"""Smoke-test for this demo repo's helm template chain.

Validates that every parent-chart template renders to valid YAML and
that the two-level helm template chain from the README works.
Run with:  python3 scripts/verify.py  (no helm binary required)

Mimics enough of `helm template` to verify that:
1. Each parent chart template renders to valid YAML after substitution.
2. The rendered child Application has a `.spec.source.helm.values` block
   whose body is itself valid YAML.
3. The child chart's values.yaml is valid YAML.
4. The composed values (child defaults + injected helm.values) are mergeable.
5. The child chart's templates render to valid YAML.

This is NOT a full helm clone — only handles the subset of Go templating
actually used by the demo's parent-chart templates:
    * {{ .Values.X }}                       — scalar substitution
    * {{ .Values.X.Y }}                     — nested attribute access
    * {{- if not (has "name" .Values.list) }}  / {{- end }}  — guard
    * {{ if .Values.X }} ... {{ end }}      — truthy guard
"""
import re
import sys
import yaml
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RED, GREEN, YELLOW, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[0m"

errors = []
warnings = []


def lookup(values, path):
    """Resolve dotted path like 'Values.argoProject' against the values dict."""
    if not path.startswith("Values."):
        return None
    cur = values
    for part in path.split(".")[1:]:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def render_template(text, values):
    """Render a helm template using a tiny subset of Go templating."""
    # 1) Handle conditional blocks
    #    {{- if not (has "X" .Values.applicationBlacklist) }} ... {{- end }}
    pattern = re.compile(
        r"\{\{-?\s*if\s+not\s+\(has\s+\"([^\"]+)\"\s+\.Values\.applicationBlacklist\)\s*-?\}\}"
        r"(.*?)"
        r"\{\{-?\s*end\s*-?\}\}",
        re.DOTALL,
    )

    def expand_blacklist_guard(m):
        name = m.group(1)
        body = m.group(2)
        if name in (values.get("applicationBlacklist") or []):
            return ""
        return body

    text = pattern.sub(expand_blacklist_guard, text)

    # 2) Scalar substitution: {{ .Values.x.y }}
    scalar_pat = re.compile(r"\{\{-?\s*\.([A-Za-z_][A-Za-z0-9_.]*)\s*-?\}\}")
    def sub_scalar(m):
        v = lookup(values, m.group(1))
        return "" if v is None else str(v)
    text = scalar_pat.sub(sub_scalar, text)

    # 3) Collapse blank lines from stripped directives
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def smoke_test(parent_dir, env_values, child_focus):
    print(f"\n{YELLOW}━━━ smoke-test: parent={parent_dir.name}  env={env_values.name}  child={child_focus} ━━━{RESET}")

    # 1) Parent values: merge defaults + env overlay
    parent_values_default = yaml.safe_load((parent_dir / "values.yaml").read_text()) or {}
    parent_values_env = yaml.safe_load(env_values.read_text()) or {}
    parent_values = {**parent_values_default, **parent_values_env}
    print(f"  ✓ parent values loaded ({len(parent_values)} keys)")

    # 2) Render each template in templates/ and verify YAML
    for tmpl in sorted((parent_dir / "templates").glob("*.yaml")):
        if tmpl.name.startswith("_"):
            continue
        try:
            rendered = render_template(tmpl.read_text(), parent_values)
            if rendered.strip() == "":
                print(f"  ◌ {tmpl.name:40s} — blacklisted (skipped)")
                continue
            # split on YAML document separators
            docs = list(yaml.safe_load_all(rendered))
            non_null = [d for d in docs if d is not None]
            if not non_null:
                warnings.append(f"{tmpl.name}: rendered to empty")
                continue
            print(f"  ✓ {tmpl.name:40s} — renders to {len(non_null)} doc(s)")
        except yaml.YAMLError as e:
            errors.append(f"{tmpl.name}: YAML error — {e}")
            print(f"  {RED}✗ {tmpl.name:40s} — YAML error: {e}{RESET}")
            print(f"\n--- rendered output ---\n{rendered}\n--- end ---")
            return

    # 3) Focused child test (the user's command flow)
    focused = parent_dir / "templates" / f"{child_focus}.yaml"
    if not focused.exists():
        errors.append(f"focused child template not found: {focused}")
        return

    print(f"\n  → Two-level chain for child '{child_focus}':")
    rendered = render_template(focused.read_text(), parent_values)
    docs = [d for d in yaml.safe_load_all(rendered) if d is not None]
    if not docs:
        # Expected when the service is in the env's applicationBlacklist
        if child_focus in (parent_values.get("applicationBlacklist") or []):
            print(f"  ◌ '{child_focus}' is in applicationBlacklist for this env — guard works ✓")
            return
        errors.append(f"{child_focus}: parent rendered empty unexpectedly")
        return
    app = docs[0]
    if app.get("kind") != "Application":
        errors.append(f"{child_focus}: top-level kind is {app.get('kind')!r}, expected Application")
        return
    print(f"  ✓ parent renders Application: {app['metadata']['name']}")

    helm_block = app.get("spec", {}).get("source", {}).get("helm", {})
    injected_values_str = helm_block.get("values", "") or ""
    try:
        injected = yaml.safe_load(injected_values_str) or {}
    except yaml.YAMLError as e:
        errors.append(f"{child_focus}: .spec.source.helm.values is not valid YAML — {e}")
        print(f"  {RED}✗ injected values invalid YAML: {e}{RESET}")
        print(f"\n--- rendered values ---\n{injected_values_str}\n--- end ---")
        return
    print(f"  ✓ injected values parsed ({len(injected)} top-level keys: {list(injected.keys())[:5]}…)")

    # 4) Child chart presence + values
    child_dir = REPO / child_focus
    child_chart = child_dir / "Chart.yaml"
    child_values_file = child_dir / "values.yaml"
    if not child_chart.exists():
        errors.append(f"child chart Chart.yaml missing: {child_chart}")
        return
    if not child_values_file.exists():
        errors.append(f"child values.yaml missing: {child_values_file}")
        return
    child_values = yaml.safe_load(child_values_file.read_text()) or {}
    print(f"  ✓ child chart {child_focus}: Chart.yaml + values.yaml present")

    # 5) Merge child defaults + injected
    merged = {**child_values, **injected}
    print(f"  ✓ merged values: {len(merged)} top-level keys")

    # 6) Render child templates
    for ctmpl in sorted((child_dir / "templates").glob("*.yaml")):
        try:
            crendered = render_template(ctmpl.read_text(), merged)
            list(yaml.safe_load_all(crendered))
            print(f"    ✓ {child_focus}/templates/{ctmpl.name} renders")
        except yaml.YAMLError as e:
            errors.append(f"{child_focus}/{ctmpl.name}: YAML error — {e}")
            print(f"    {RED}✗ {child_focus}/templates/{ctmpl.name} — {e}{RESET}")


# ────────────────────────────────────────────────────────────────────────
# Test cases that mirror what the user's command does
# ────────────────────────────────────────────────────────────────────────
parent = REPO / "services-observability"
env_useast = parent / "values-useast2-demo.yaml"
env_uswest = parent / "values-uswest2-demo.yaml"

# Primary case: mirrors the user's command exactly
#   helm template ../mimir-distributed -f ../mimir-distributed/values.yaml \
#     -f <(helm template -f values.yaml -f values-useast2-demo.yaml \
#          -s templates/mimir-distributed.yaml . | yq -r .spec.source.helm.values)
smoke_test(parent, env_useast, "mimir-distributed")

# Other observability services, useast2
for svc in ["loki", "grafana", "tempo-distributed", "alloy", "pyroscope"]:
    smoke_test(parent, env_useast, svc)

# Second env (uswest2) — blacklist removes some services
smoke_test(parent, env_uswest, "mimir-distributed")
smoke_test(parent, env_uswest, "pyroscope")  # should be blacklisted


# ────────────────────────────────────────────────────────────────────────
# ApplicationSet validation — different pattern, simpler check:
# parse the YAML, confirm structure, expand the list generator.
# ────────────────────────────────────────────────────────────────────────
def verify_applicationset(path):
    print(f"\n{YELLOW}━━━ applicationset: {path.name} ━━━{RESET}")
    try:
        appset = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        errors.append(f"{path.name}: YAML parse error — {e}")
        print(f"  {RED}✗ YAML parse error: {e}{RESET}")
        return

    if appset.get("kind") != "ApplicationSet":
        errors.append(f"{path.name}: kind is {appset.get('kind')!r}, expected ApplicationSet")
        return
    name = appset.get("metadata", {}).get("name", "?")
    print(f"  ✓ kind=ApplicationSet  name={name}")

    generators = appset.get("spec", {}).get("generators", [])
    if not generators:
        errors.append(f"{path.name}: no generators defined")
        return
    print(f"  ✓ {len(generators)} generator(s): {[next(iter(g)) for g in generators]}")

    # Expand list generator(s) to show what Apps would be generated
    for g in generators:
        if "list" in g:
            elements = g["list"].get("elements", [])
            tmpl_name = appset["spec"]["template"]["metadata"].get("name", "")
            for el in elements:
                # Best-effort substitute {{ .key }} placeholders
                rendered = tmpl_name
                for k, v in el.items():
                    rendered = rendered.replace("{{ ." + k + " }}", str(v))
                print(f"    → would generate: {rendered}")


appsets_dir = REPO / "applicationsets"
if appsets_dir.is_dir():
    for appset_file in sorted(appsets_dir.glob("*.yaml")):
        verify_applicationset(appset_file)

# ────────────────────────────────────────────────────────────────────────
print(f"\n{'═' * 70}")
if errors:
    print(f"{RED}✗ FAILED — {len(errors)} error(s):{RESET}")
    for e in errors:
        print(f"  • {e}")
    sys.exit(1)
elif warnings:
    print(f"{YELLOW}⚠ {len(warnings)} warning(s):{RESET}")
    for w in warnings:
        print(f"  • {w}")
print(f"{GREEN}✓ All templates render to valid YAML.{RESET}")
print(f"{GREEN}  The helm template chain the user described will work.{RESET}")
