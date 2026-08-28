#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ansible_root="${repository_root}/ansible"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

export ANSIBLE_CONFIG="${ansible_root}/ansible.cfg"
export ANSIBLE_LOCAL_TEMP="${temporary_directory}/local"
export ANSIBLE_REMOTE_TEMP="${temporary_directory}/remote"
mkdir -p "${ANSIBLE_LOCAL_TEMP}" "${ANSIBLE_REMOTE_TEMP}"

cd "${ansible_root}"

yamllint .
ansible-lint playbooks roles
ansible-inventory --graph

for playbook in playbooks/*.yml playbooks/network/*.yaml; do
  ansible-playbook --syntax-check "${playbook}"
done

python3 "${repository_root}/scripts/validate_network.py"
