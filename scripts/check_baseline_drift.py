#!/usr/bin/env python3
"""Baseline drift check for the HugMesh metapom.

Reads the Spring Boot parent version and the Spring Cloud train from this
repo's pom.xml and compares them with the pom.xml found on each consumer
repo's ref (default origin/main). Exits 1 on drift, 2 when a consumer cannot
be read (a missing checkout or ref is not reported as clean).

A consumer that parents on net.hugmesh:hugmesh-parent must name this pom's own
version. A consumer that parents on spring-boot-starter-parent directly must
name the same Boot version. A consumer that sets spring-cloud.version must set
the same train.

Other shared pins (springdoc, resilience4j, aws.sdk, testcontainers,
hugmesh-commons) are listed as notes when a consumer overrides them with a
different value; notes never change the exit status.

Usage: scripts/check_baseline_drift.py [--root DIR] [--ref REF] [REPO ...]
"""
import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://maven.apache.org/POM/4.0.0}"
BOOT = ("org.springframework.boot", "spring-boot-starter-parent")
METAPOM = ("net.hugmesh", "hugmesh-parent")
CLOUD = "spring-cloud.version"
SHARED = (
    "springdoc.version",
    "resilience4j.version",
    "aws.sdk.version",
    "testcontainers.version",
    "hugmesh-commons.version",
)
COMMONS = ("net.hugmesh", "hugmesh-commons")

DEFAULT_CONSUMERS = (
    "hugmesh-gateway",
    "hugmesh-be-gateway",
    "hugmesh-fe-gateway",
    "hugmesh-actions",
    "hugmesh-remote-fragment",
    "hugmesh-admin-bff-api",
    "hugmesh-auth-core",
    "hugmesh-character-forge-bff-api",
    "hugmesh-commons",
    "hugmesh-federation-api",
    "hugmesh-forum-bff-api",
    "hugmesh-mesh-bff-api",
    "hugmesh-mod-bff-api",
    "hugmesh-owncast-bff-api",
    "hugmesh-tube-bff-api",
    "hugmesh-user-bff-api",
    "hugmesh-wiki-bff-api",
)


class Unreadable(Exception):
    """A consumer's pom could not be read (as opposed to being absent)."""


def _text(node, tag):
    child = node.find(NS + tag)
    return child.text.strip() if child is not None and child.text else None


def parse(pom_xml):
    """Return the facts the check compares, from the text of one pom.xml."""
    root = ET.fromstring(pom_xml)
    parent = root.find(NS + "parent")
    parent_key = parent_version = None
    if parent is not None:
        parent_key = (_text(parent, "groupId"), _text(parent, "artifactId"))
        parent_version = _text(parent, "version")
    props = {}
    props_node = root.find(NS + "properties")
    if props_node is not None:
        for p in props_node:
            props[p.tag.replace(NS, "")] = (p.text or "").strip()
    commons_pins = []
    for dep in root.iter(NS + "dependency"):
        if (_text(dep, "groupId"), _text(dep, "artifactId")) == COMMONS:
            version = _text(dep, "version")
            if version and not version.startswith("${"):
                commons_pins.append(version)
    return {
        "parent_key": parent_key,
        "parent_version": parent_version,
        "own_version": _text(root, "version"),
        "props": props,
        "commons_pins": commons_pins,
    }


def compare(base, consumers):
    """Return (drift, notes). consumers maps repo name -> pom text or None."""
    drift, notes = [], []
    for name, pom_xml in consumers.items():
        if pom_xml is None:
            notes.append(f"{name}: no pom.xml on the ref, skipped")
            continue
        facts = parse(pom_xml)
        key, got = facts["parent_key"], facts["parent_version"]
        if key == METAPOM:
            if got != base["own_version"]:
                drift.append(
                    f"{name}: parent hugmesh-parent {got}, this pom is "
                    f"{base['own_version']}"
                )
        elif key == BOOT:
            if got != base["parent_version"]:
                drift.append(
                    f"{name}: Spring Boot {got}, this pom is "
                    f"{base['parent_version']}"
                )
        else:
            notes.append(f"{name}: parent {key} is not a Boot or metapom parent")
        cloud = facts["props"].get(CLOUD)
        if cloud is not None and cloud != base["props"].get(CLOUD):
            drift.append(
                f"{name}: {CLOUD} {cloud}, this pom is {base['props'].get(CLOUD)}"
            )
        for prop in SHARED:
            mine, theirs = base["props"].get(prop), facts["props"].get(prop)
            if theirs is not None and theirs != mine:
                notes.append(f"{name}: {prop} {theirs}, this pom is {mine}")
        commons = base["props"].get("hugmesh-commons.version")
        for pin in facts["commons_pins"]:
            if pin != commons:
                notes.append(
                    f"{name}: hugmesh-commons dependency {pin}, this pom is {commons}"
                )
    return drift, notes


def read_ref_pom(checkout, ref):
    """Text of pom.xml at ref, None if the ref has no pom, Unreadable if the
    checkout or the ref is missing."""
    git = ["git", "-C", str(checkout)]
    if not checkout.is_dir():
        raise Unreadable(f"{checkout} is not a directory")
    probe = subprocess.run(
        git + ["rev-parse", "--verify", "--quiet", ref + "^{commit}"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        raise Unreadable(f"{checkout}: ref {ref} not found")
    shown = subprocess.run(
        git + ["cat-file", "-e", f"{ref}:pom.xml"], capture_output=True, text=True
    )
    if shown.returncode != 0:
        return None
    out = subprocess.run(
        git + ["show", f"{ref}:pom.xml"], capture_output=True, text=True
    )
    if out.returncode != 0:
        raise Unreadable(f"{checkout}: git show {ref}:pom.xml failed")
    return out.stdout


def main(argv=None):
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("repos", nargs="*", help="consumer repo names")
    ap.add_argument("--root", type=Path, default=here.parent,
                    help="directory holding the consumer checkouts")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--pom", type=Path, default=here / "pom.xml",
                    help="the metapom to compare against")
    args = ap.parse_args(argv)

    base = parse(args.pom.read_text(encoding="utf-8"))
    if base["parent_key"] != BOOT or not base["parent_version"]:
        print(f"{args.pom}: no Spring Boot parent version found", file=sys.stderr)
        return 2
    consumers, unreadable = {}, []
    for name in args.repos or DEFAULT_CONSUMERS:
        try:
            consumers[name] = read_ref_pom(args.root / name, args.ref)
        except Unreadable as exc:
            unreadable.append(str(exc))
    drift, notes = compare(base, consumers)
    for line in notes:
        print("note:", line)
    for line in drift:
        print("DRIFT:", line)
    for line in unreadable:
        print("UNREADABLE:", line, file=sys.stderr)
    if unreadable:
        return 2
    if drift:
        return 1
    print(
        f"ok: {sum(v is not None for v in consumers.values())} consumers on Boot {base['parent_version']}, "
        f"hugmesh-parent {base['own_version']}, "
        f"{CLOUD} {base['props'].get(CLOUD)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
