# Everlab CI/CD Portfolio Guide

This public repository is a sanitized, history-free portfolio snapshot. GitHub
Actions validates the material, but this repository has no credentials and no
connection to the Everlab production cluster.

## Publication and Delivery Boundaries

```text
private feature branch -> private CI -> review -> private main -> Argo CD
                                                     |
                                                     `-> reviewed export
                                                           |
                                                           `-> public snapshot -> GitHub CI
```

The private repository is the production source of truth. The public snapshot
demonstrates the same infrastructure patterns after a separate content and
security review. It is never configured as an automatic mirror because a
literal mirror could publish material that is intentionally private.

## Public Validation

The workflow in `.github/workflows/validate.yml` runs on pull requests, pushes
to `main`, and manual dispatches with read-only repository permissions. A
single consolidated `Portfolio validation` job avoids duplicate runner setup
while checking:

- YAML, repository text, and the Argo CD application graph
- all Kustomize builds and Kubernetes schemas
- storage and CloudNativePG safety rules
- Ansible lint, inventory, playbook syntax, and worker networking
- Gitleaks, actionlint, ShellCheck, and the infrastructure SVG

Protect `main` in GitHub with pull requests and `Portfolio validation` as a
required check. Prevent force pushes during normal development. A history-free
publication replacement is a separate, reviewed maintenance operation.

## Local Validation

Run the applicable repository checks before opening a pull request:

```bash
python3 scripts/validate_text.py
python3 scripts/validate_gitops.py
scripts/validate_kustomize.sh
scripts/validate_ansible.sh
git diff --check
```

CI success proves that the snapshot is internally consistent and renderable.
It does not prove that a live custom resource, external service, or physical
device will accept the configuration.

## Production Delivery Model

In the private operational repository, merging to `main` is the Kubernetes
delivery trigger. The `everlab-prod` root Application discovers changes through
the app-of-apps graph, and child Applications retain their own automated-sync,
pruning, retry, and sync-wave settings.

Production CI remains read-only:

- Argo CD is the only automated Kubernetes deployment mechanism.
- CI does not run `kubectl apply` or `argocd app sync`.
- CI does not receive a kubeconfig or production secret.
- Stateful resources retain their pruning and deletion protections.
- Operators monitor affected Applications until they are `Synced` and
  `Healthy` after merge.

Ansible is validated by CI but applied manually because it can change host
networking, packages, and cluster membership. Connectivity-sensitive changes
are applied to one host first with out-of-band console access available.

## Publishing a New Snapshot

Every publication starts from a reviewed private commit and creates a new
orphan root commit. Production Git history, ignored vault files, local
credentials, and generated secrets are never copied.

The private repository's publisher performs this process:

1. Export tracked files only.
2. Apply the reviewed exclusion policy and public-only templates.
3. Remove every related manifest, app-of-apps registration, catalog entry,
   monitoring target, and documentation reference.
4. Rewrite repository URLs for the public repository.
5. Audit the complete tree and scan it with Gitleaks.
6. Create and inspect one orphan root commit.
7. Replace the prior public root with an exact `--force-with-lease` guard.
8. Wait for the consolidated GitHub validation job.

The public repository must never be added to the production Argo CD bootstrap
or receive deployment credentials.
