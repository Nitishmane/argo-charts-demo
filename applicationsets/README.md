# ApplicationSets

The companion pattern to **App-of-Apps**.

Where the App-of-Apps pattern (`services-observability/` in this repo)
uses Helm to generate Application manifests *at deploy time*, an
**ApplicationSet** is a native ArgoCD CRD that generates Applications
*dynamically at runtime* from a generator.

> When App-of-Apps starts to feel like "I'm writing more Helm just to
> stamp out YAML," reach for an ApplicationSet.

---

## The example: `external-dns.yaml`

A single ApplicationSet that deploys **external-dns** into the cluster
twice — once for the **public** DNS zone, once for the **private** zone —
with the same chart and slightly different config per zone.

### Apply it

```bash
kubectl apply -f applicationsets/external-dns.yaml
```

### What gets generated

ArgoCD reads the `list` generator and expands the `template:` once per
element. With two elements, two Applications are born:

```
uswest2-external-dns-public    →  external-dns chart, aws-zone-type=public,  txtOwnerId=…-public
uswest2-external-dns-private   →  external-dns chart, aws-zone-type=private, txtOwnerId=…-private
```

Add a third element and you get a third Application — no template edit
required.

### Anatomy

```yaml
spec:
  generators:           # ← what to iterate over
    - list:
        elements:
          - zoneType: public
          - zoneType: private

  template:             # ← what to render per element
    metadata:
      name: "uswest2-external-dns-{{ .zoneType }}"
    spec:
      …
      source:
        chart: external-dns
        helm:
          valuesObject:
            extraArgs:
              - --aws-zone-type={{ .zoneType }}
            …
```

The `{{ .zoneType }}` placeholders are substituted from the list
element's keys (`goTemplate: true` switches to native Go template
semantics, which matches the rest of Helm).

---

## Where this scales

ApplicationSets really shine with **non-list generators**, which is the
story slide 14–15 of the talk tells:

| Generator | Iterates over | Use it for |
|-----------|---------------|------------|
| `list` | Inline elements | This file — small, hand-curated sets |
| `clusters` | Cluster Secrets labelled with selectors | "Deploy X to every cluster tagged `env=prod`" |
| `git` | Files / directories in a Git repo | "One Application per `clusters/*.yaml`" |
| `matrix` | Cross-product of any two generators | `4 charts × 12 clusters = 48 Applications` |
| `pullRequest` | Open PRs in a repo | Ephemeral preview environments |

The classic scale-up pattern is **`matrix(list, clusters)`** — a list
of charts crossed with a cluster selector — which is what generates
the "48 Applications from one CRD" example in the talk.

---

## ApplicationSet vs App-of-Apps — when to use which

| | App-of-Apps | ApplicationSet |
|---|---|---|
| Mechanism | Helm chart of `Application` manifests | Native CRD with generators |
| Dynamic discovery? | No — must list each child | Yes — `clusters`/`git` generators |
| Adding a target | Edit template/values + PR | Add a label / a file |
| Best for | A bounded service catalog (this repo's `services-observability`) | Anything that scales by cluster, environment, or PR |

The two patterns compose well — many platforms use both: App-of-Apps to
declare a curated stack, ApplicationSet to fan that stack out across
clusters.

---

## Verify locally

The repo's `scripts/verify.py` also validates every file in this folder
parses as a well-formed ApplicationSet:

```bash
python3 scripts/verify.py
```
