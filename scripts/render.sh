#!/usr/bin/env bash
# Render a child Application + the workloads it would deploy.
#
# Usage:
#   ./scripts/render.sh <parent-chart> <env-suffix> <child-template>
#
# Example:
#   ./scripts/render.sh services-observability useast2-demo mimir-distributed
set -euo pipefail

PARENT="${1:?parent chart name required, e.g. services-observability}"
ENV="${2:?env suffix required, e.g. useast2-demo}"
CHILD="${3:?child template name required, e.g. mimir-distributed}"

cd "$(dirname "$0")/.."

if ! command -v yq >/dev/null; then
    echo "ERROR: yq is required (https://github.com/mikefarah/yq)" >&2
    exit 1
fi

cd "${PARENT}"

# First, show the parent's rendered child Application
echo "════════════════════════════════════════════════════════════════════"
echo "Child Application that the parent (${PARENT}) creates for ${ENV}:"
echo "════════════════════════════════════════════════════════════════════"
helm template . \
    -f values.yaml \
    -f "values-${ENV}.yaml" \
    -s "templates/${CHILD}.yaml"

# Then, render the workloads the child Application would actually deploy
echo "════════════════════════════════════════════════════════════════════"
echo "Workloads the ${CHILD} child Application would deploy:"
echo "════════════════════════════════════════════════════════════════════"
helm template "../${CHILD}" \
    -f "../${CHILD}/values.yaml" \
    -f <(helm template . \
            -f values.yaml \
            -f "values-${ENV}.yaml" \
            -s "templates/${CHILD}.yaml" \
            | yq -r '.spec.source.helm.values // ""')
