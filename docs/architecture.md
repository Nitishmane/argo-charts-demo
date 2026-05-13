# Architecture

## App-of-Apps flow

```mermaid
flowchart LR
    Root["Root Application<br/>(apps/services-observability-useast2-demo.yaml)"]
    Root --> Parent["Parent chart<br/>services-observability/<br/>(this repo)"]

    Parent --> A1["Application: alloy"]
    Parent --> A2["Application: grafana"]
    Parent --> A3["Application: loki"]
    Parent --> A4["Application: mimir-distributed"]
    Parent --> A5["Application: pyroscope"]
    Parent --> A6["Application: tempo-distributed"]
    Parent --> A7["Application: opentelemetry-demo"]

    A1 --> C1["chart: alloy/"]
    A2 --> C2["chart: grafana/"]
    A3 --> C3["chart: loki/"]
    A4 --> C4["chart: mimir-distributed/"]
    A5 --> C5["chart: pyroscope/"]
    A6 --> C6["chart: tempo-distributed/"]
    A7 --> C7["chart: opentelemetry-demo/"]
```

## Per-env diff

| Knob | `values-useast2-demo.yaml` | `values-uswest2-demo.yaml` |
|------|----------------------------|----------------------------|
| `region` | `us-east-2` | `us-west-2` |
| `server` | `<useast2 EKS endpoint>` | `<uswest2 EKS endpoint>` |
| S3 buckets | `acme-*-us-east-2-demo` | `acme-*-us-west-2-demo` |
| `applicationBlacklist` | `[]` | `[opentelemetry-demo, pyroscope]` |

Same templates, different DNA.
