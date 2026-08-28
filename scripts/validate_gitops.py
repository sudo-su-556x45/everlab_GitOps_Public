#!/usr/bin/env python3
"""Validate Everlab repository invariants that generic linters cannot express."""

from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
KUBERNETES_ROOT = ROOT / "kubernetes"
SYNC_OPTIONS = "argocd.argoproj.io/sync-options"
LOCAL_REPOSITORY = "everlab_GitOps_Public.git"


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML mapping keys instead of silently replacing them."""


def construct_mapping(
    loader: UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_mapping,
)


def yaml_files() -> Iterable[Path]:
    yield from sorted(KUBERNETES_ROOT.rglob("*.yaml"))
    yield from sorted(KUBERNETES_ROOT.rglob("*.yml"))


def load_documents(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [doc for doc in yaml.load_all(stream, Loader=UniqueKeyLoader) if isinstance(doc, dict)]


def sync_options(resource: dict[str, Any]) -> set[str]:
    annotations = resource.get("metadata", {}).get("annotations", {})
    value = annotations.get(SYNC_OPTIONS, "")
    return {option.strip() for option in str(value).split(",") if option.strip()}


def resource_label(path: Path, resource: dict[str, Any]) -> str:
    name = resource.get("metadata", {}).get("name", "<unnamed>")
    return f"{path.relative_to(ROOT)}: {resource.get('kind', '<unknown>')}/{name}"


def validate_storage(
    resources: list[tuple[Path, dict[str, Any]]],
    errors: list[str],
) -> None:
    retained_storage_classes: set[str] = set()
    for path, resource in resources:
        if resource.get("kind") != "StorageClass":
            continue
        name = resource.get("metadata", {}).get("name", "")
        if resource.get("reclaimPolicy") != "Retain":
            errors.append(f"{resource_label(path, resource)} must use reclaimPolicy: Retain")
        else:
            retained_storage_classes.add(name)

    for path, resource in resources:
        kind = resource.get("kind")
        options = sync_options(resource)
        if kind == "PersistentVolumeClaim":
            required = {"Prune=false", "Delete=false"}
            missing = required - options
            if missing:
                errors.append(
                    f"{resource_label(path, resource)} is missing sync options: "
                    f"{', '.join(sorted(missing))}"
                )

        if kind == "Cluster" and resource.get("apiVersion", "").startswith("postgresql.cnpg.io/"):
            spec = resource.get("spec", {})
            if "pvcRetentionPolicy" in spec:
                errors.append(
                    f"{resource_label(path, resource)} uses unsupported spec.pvcRetentionPolicy"
                )
            if "Prune=false" not in options:
                errors.append(f"{resource_label(path, resource)} must be prune-protected")
            for storage_key in ("storage", "walStorage"):
                storage = spec.get(storage_key)
                if not isinstance(storage, dict):
                    continue
                storage_class = storage.get("storageClass")
                if storage_class and storage_class not in retained_storage_classes:
                    errors.append(
                        f"{resource_label(path, resource)} references non-retained or unknown "
                        f"StorageClass {storage_class!r}"
                    )


def validate_kustomizations(errors: list[str]) -> Counter[Path]:
    application_references: Counter[Path] = Counter()
    for kustomization_path in sorted(KUBERNETES_ROOT.rglob("kustomization.yaml")):
        documents = load_documents(kustomization_path)
        if len(documents) != 1:
            errors.append(f"{kustomization_path.relative_to(ROOT)} must contain one document")
            continue
        for resource_path in documents[0].get("resources", []) or []:
            if not isinstance(resource_path, str) or "://" in resource_path:
                continue
            resolved = (kustomization_path.parent / resource_path).resolve()
            if not resolved.exists():
                errors.append(
                    f"{kustomization_path.relative_to(ROOT)} references missing path {resource_path!r}"
                )
                continue
            if resolved.is_dir() and not (resolved / "kustomization.yaml").is_file():
                errors.append(
                    f"{kustomization_path.relative_to(ROOT)} references directory "
                    f"{resource_path!r} without kustomization.yaml"
                )
            if resolved.is_file() and resolved.name == "application.yaml":
                application_references[resolved] += 1
    return application_references


def application_sources(resource: dict[str, Any]) -> list[dict[str, Any]]:
    spec = resource.get("spec", {})
    if isinstance(spec.get("source"), dict):
        return [spec["source"]]
    return [source for source in spec.get("sources", []) if isinstance(source, dict)]


def validate_applications(
    resources: list[tuple[Path, dict[str, Any]]],
    references: Counter[Path],
    errors: list[str],
) -> None:
    application_files = set(KUBERNETES_ROOT.rglob("application.yaml"))
    for application_path in sorted(application_files):
        count = references[application_path.resolve()]
        if count != 1:
            errors.append(
                f"{application_path.relative_to(ROOT)} is registered {count} times; expected exactly once"
            )

    names: Counter[str] = Counter()
    for path, resource in resources:
        if resource.get("kind") != "Application":
            continue
        name = resource.get("metadata", {}).get("name", "")
        names[name] += 1
        if resource.get("metadata", {}).get("namespace") != "argocd":
            errors.append(f"{resource_label(path, resource)} must be in the argocd namespace")
        for source in application_sources(resource):
            if LOCAL_REPOSITORY not in str(source.get("repoURL", "")):
                continue
            source_path = source.get("path")
            if not source_path:
                continue
            resolved = ROOT / source_path
            if not resolved.is_dir():
                errors.append(
                    f"{resource_label(path, resource)} references missing local path {source_path!r}"
                )
            elif not (resolved / "kustomization.yaml").is_file():
                errors.append(
                    f"{resource_label(path, resource)} local path {source_path!r} has no "
                    "kustomization.yaml"
                )

    for name, count in names.items():
        if name and count > 1:
            errors.append(f"Argo CD Application name {name!r} is declared {count} times")


def validate_workload_selectors(
    resources: list[tuple[Path, dict[str, Any]]],
    errors: list[str],
) -> None:
    for path, resource in resources:
        if resource.get("kind") not in {"Deployment", "StatefulSet", "DaemonSet"}:
            continue
        spec = resource.get("spec", {})
        selector = spec.get("selector", {}).get("matchLabels", {})
        pod_labels = spec.get("template", {}).get("metadata", {}).get("labels", {})
        if selector and any(pod_labels.get(key) != value for key, value in selector.items()):
            errors.append(
                f"{resource_label(path, resource)} selector does not match its pod-template labels"
            )


def validate_tracked_secrets(errors: list[str]) -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    forbidden_names = {"vault.yml", ".vault-password", ".vault_password"}
    for tracked_path in result.stdout.splitlines():
        path = Path(tracked_path)
        if path.name in forbidden_names or path.name.startswith(".vault-password"):
            errors.append(f"secret-bearing file must not be tracked: {tracked_path}")


def main() -> int:
    errors: list[str] = []
    resources: list[tuple[Path, dict[str, Any]]] = []
    parsed_files = 0

    for path in yaml_files():
        try:
            documents = load_documents(path)
        except yaml.YAMLError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        parsed_files += 1
        resources.extend((path, document) for document in documents if document.get("kind"))

    validate_storage(resources, errors)
    references = validate_kustomizations(errors)
    validate_applications(resources, references, errors)
    validate_workload_selectors(resources, errors)
    validate_tracked_secrets(errors)

    if errors:
        print("GitOps validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(
        f"GitOps validation passed: {parsed_files} YAML files, "
        f"{len(resources)} Kubernetes resources, and {len(references)} Application registrations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
