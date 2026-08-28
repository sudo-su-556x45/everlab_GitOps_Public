#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

if command -v kustomize > /dev/null 2>&1; then
  build_command=(kustomize build)
elif command -v kubectl > /dev/null 2>&1; then
  build_command=(kubectl kustomize)
else
  echo "kustomize or kubectl is required" >&2
  exit 1
fi

mapfile -t kustomizations < <(
  find "${repository_root}/kubernetes" -name kustomization.yaml -print | sort
)

for kustomization in "${kustomizations[@]}"; do
  directory="$(dirname "${kustomization}")"
  relative_directory="${directory#"${repository_root}/"}"
  output_file="${temporary_directory}/$(printf '%s' "${relative_directory}" | tr '/' '_').yaml"

  echo "Building ${relative_directory}"
  "${build_command[@]}" "${directory}" > "${output_file}"

  if [[ -s "${output_file}" ]]; then
    kubeconform \
      -ignore-missing-schemas \
      -kubernetes-version 1.33.0 \
      -strict \
      -summary \
      "${output_file}"
  fi
done

echo "Validated ${#kustomizations[@]} Kustomizations"
