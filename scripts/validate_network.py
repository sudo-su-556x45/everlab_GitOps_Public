#!/usr/bin/env python3
"""Render and verify the static VLAN configuration for every lab worker."""

from __future__ import annotations

import ipaddress
import sys
from pathlib import Path
from typing import Any

import jinja2
import yaml


ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_ROOT = ROOT / "ansible"
INVENTORY_PATH = ANSIBLE_ROOT / "inventories/prod/hosts.yml"
VARS_PATH = ANSIBLE_ROOT / "inventories/prod/group_vars/k8s.yml"
TEMPLATE_PATH = ANSIBLE_ROOT / "playbooks/network/templates/interfaces.j2"


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a YAML mapping")
    return value


def worker_hosts(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    children = inventory["all"]["children"]
    worker_groups = children["k8s_workers"]["children"]
    workers: dict[str, dict[str, Any]] = {}
    for group_name in worker_groups:
        for host, host_vars in children[group_name]["hosts"].items():
            workers[host] = host_vars
    return workers


def required_line(rendered: str, line: str, host: str, errors: list[str]) -> None:
    if line not in rendered.splitlines():
        errors.append(f"{host}: rendered interfaces file is missing {line!r}")


def main() -> int:
    inventory = load_yaml(INVENTORY_PATH)
    variables = load_yaml(VARS_PATH)
    workers = worker_hosts(inventory)
    template = jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_PATH.parent),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
    ).get_template(TEMPLATE_PATH.name)

    errors: list[str] = []
    assigned_addresses: set[ipaddress.IPv4Address] = set()
    vlans = {
        "management": variables["k8s_network_management_vlan"],
        "cluster": variables["k8s_network_cluster_vlan"],
        "load_balancer": variables["k8s_network_load_balancer_vlan"],
        "storage": variables["k8s_network_storage_vlan"],
        "pv": variables["k8s_network_pv_vlan"],
    }

    for host, host_vars in sorted(workers.items()):
        management_ip = ipaddress.ip_address(host_vars["ansible_host"])
        cluster_ip = ipaddress.ip_address(host_vars["k8s_cluster_ip"])
        last_octet = int(str(cluster_ip).split(".")[-1])
        expected_management_ip = ipaddress.ip_address(
            f"192.168.{vlans['management']}.{last_octet}"
        )
        if management_ip != expected_management_ip:
            errors.append(
                f"{host}: management address {management_ip} does not match derived "
                f"address {expected_management_ip}"
            )

        addresses = {
            name: ipaddress.ip_address(f"192.168.{vlan}.{last_octet}")
            for name, vlan in vlans.items()
        }
        for address in addresses.values():
            if address in assigned_addresses:
                errors.append(f"{host}: duplicate rendered address {address}")
            assigned_addresses.add(address)

        context = {
            **variables,
            "management_static_ip": str(addresses["management"]),
            "kubernetes_static_ip": str(addresses["cluster"]),
            "applications_static_ip": str(addresses["load_balancer"]),
            "nfs_static_ip": str(addresses["storage"]),
            "pv_static_ip": str(addresses["pv"]),
        }
        rendered = template.render(context)
        interface = variables["k8s_network_physical_interface"]
        prefix = variables["k8s_network_prefix"]

        required_line(rendered, "source /etc/network/interfaces.d/*", host, errors)
        required_line(rendered, f"allow-hotplug {interface}", host, errors)
        required_line(rendered, f"    address {addresses['management']}/{prefix}", host, errors)
        required_line(rendered, f"    address {addresses['cluster']}/{prefix}", host, errors)
        required_line(rendered, f"    address {addresses['load_balancer']}/{prefix}", host, errors)
        required_line(rendered, f"    address {addresses['storage']}/{prefix}", host, errors)
        required_line(rendered, f"    address {addresses['pv']}/{prefix}", host, errors)
        required_line(
            rendered,
            f"    gateway {variables['k8s_network_management_gateway']}",
            host,
            errors,
        )
        for route in variables["k8s_network_load_balancer_routes"]:
            route_interface = f"{interface}.{vlans['load_balancer']}"
            gateway = variables["k8s_network_load_balancer_gateway"]
            required_line(
                rendered,
                f"    post-up ip route replace {route} via {gateway} dev {route_interface}",
                host,
                errors,
            )
            required_line(
                rendered,
                f"    pre-down ip route del {route} via {gateway} dev {route_interface} || true",
                host,
                errors,
            )

    if errors:
        print("Worker network validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Worker network validation passed for {len(workers)} inventory hosts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
