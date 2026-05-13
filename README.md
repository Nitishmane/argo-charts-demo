# argo-charts-demo

Two side-by-side, runnable demos of the patterns from the IaCConf 2026 talk
**"Infrastructure at Scale with ArgoCD: Hub–Spoke, App-of-Apps, ApplicationSets."**

1. **App-of-Apps** (`services-observability/`) — one parent Helm chart that
   templates many child `Application` manifests, with per-environment value
   files and an `applicationBlacklist` to enable/disable services per env.
2. **ApplicationSet** (`applicationsets/`) — a native ArgoCD CRD that
   generates Applications dynamically from a generator (list / clusters /
   matrix / …). See [applicationsets/README.md](applicationsets/README.md).

---

## What's in here

```
argo-charts-demo/
├── apps/                            ← root Application (the "spoke entrypoint")
│   └── services-observability-useast2-demo.yaml
│
├── services-observability/          ← parent chart  (App-of-Apps for observability)
│   ├── Chart.yaml
│   ├── values.yaml                  ← chart defaults (empty)
│   ├── values-useast2-demo.yaml     ← env-specific overrides
│   ├── values-uswest2-demo.yaml     ← second env, shows multi-env
│   └── templates/
│       ├── _helpers.tpl
│       ├── alloy.yaml               ← each file = one child Application
│       ├── grafana.yaml
│       ├── loki.yaml
│       ├── mimir-distributed.yaml
│       ├── opentelemetry-demo.yaml
│       ├── pyroscope.yaml
│       └── tempo-distributed.yaml
│
├── <service>/                       ← child charts — stubs for the demo
│   ├── alloy/                       ↳ each is a real Helm chart skeleton
│   ├── grafana/                       so the helm template chain renders.
│   ├── loki/                          In production these are vendored
│   ├── mimir-distributed/             upstream charts (e.g. grafana/mimir-distributed).
│   ├── opentelemetry-demo/
│   ├── pyroscope/
│   └── tempo-distributed/
│
└── applicationsets/                 ← ApplicationSet demo (the OTHER pattern)
    ├── README.md
    └── external-dns.yaml            ← list-generator example: 2 zones → 2 Applications
```

---

## The pattern in 60 seconds

1. **Root `Application`** (in `apps/`) points ArgoCD at the parent chart and a values file.
2. **Parent chart** (`services-observability/`) is a Helm chart whose `templates/`
   directory contains ArgoCD `Application` manifests — one per child service.
3. Each child `Application` template is wrapped in a `{{- if not (has "X" .Values.applicationBlacklist) }}`
   guard so envs can opt-out of specific services.
4. The child `Application` points at the **child chart** path in this same repo
   and injects per-env Helm `values:` inline.
5. ArgoCD reconciles the parent → reconciles each child → reconciles the workloads.

The result: **adding a new region is one PR** that drops in a `values-<region>-<env>.yaml`.

---

## Try it locally

Render the parent (no cluster needed):

```bash
cd services-observability

# Show all child Applications the parent would create for useast2-demo
helm template . \
  -f values.yaml \
  -f values-useast2-demo.yaml
```

Render a specific child Application **plus** the workloads it would deploy
(the two-level chain the talk demos):

```bash
cd services-observability

helm template ../mimir-distributed \
  -f ../mimir-distributed/values.yaml \
  -f <(helm template . \
        -f values.yaml \
        -f values-useast2-demo.yaml \
        -s templates/mimir-distributed.yaml \
        | yq -r .spec.source.helm.values)
```

Or use the helper script:

```bash
chmod +x scripts/render.sh   # one-time
./scripts/render.sh services-observability useast2-demo mimir-distributed
```

### Verifying templates without installing `helm`

A tiny Python verifier checks that every parent template renders to valid YAML
and that the two-level chain above produces a parseable child Application. It
needs only `python3` + `pyyaml`:

```bash
python3 scripts/verify.py
```

Output ends with `✓ All templates render to valid YAML.` when the repo is healthy.

Skip a service via the blacklist:

```yaml
# services-observability/values-useast2-demo.yaml
applicationBlacklist:
  - opentelemetry-demo  # ← skip this one in this env
  - pyroscope
```

Add a new env in one PR:

```bash
cp services-observability/values-useast2-demo.yaml \
   services-observability/values-eu-west-1-prod.yaml
# …edit DNS, server, S3 buckets, blacklist… commit. Done.
```

---

## Deploying with ArgoCD

1. Push this repo to GitHub and update the `argoRepo` field in each
   `values-<env>.yaml` to point at it.
2. Apply the root Application:
   ```bash
   kubectl apply -f apps/services-observability-useast2-demo.yaml
   ```
3. ArgoCD does the rest.

---

## Required substitutions (search for `# TODO`)

These are the env-specific values you must replace before deploying. They're
deliberately tagged so they're easy to find:

| Value | Where | Notes |
|-------|-------|-------|
| `server` (EKS API endpoint) | `services-observability/values-<env>.yaml` | from `aws eks describe-cluster` |
| `argoRepo` | `services-observability/values-<env>.yaml` | the GitHub URL of your fork |
| `dns` | `services-observability/values-<env>.yaml` | base zone for ingress hostnames |
| `vpnCidr` | `services-observability/values-<env>.yaml` | allow-listed source IPs |
| S3 bucket names | `services-observability/templates/*.yaml` | per-region object storage |

```bash
grep -rn "# TODO" .
```

---

## Prerequisites

- Helm ≥ 3.x
- [yq](https://github.com/mikefarah/yq) (for the two-level render command)
- ArgoCD (for actual deployment; not needed for `helm template`)

## License

MIT — see [LICENSE](LICENSE).
