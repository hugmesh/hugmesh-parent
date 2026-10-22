"""Checks on pom.xml that ./mvnw validate does not make.

Run: python3 -m unittest discover -s scripts
"""
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

POM = pathlib.Path(__file__).resolve().parent.parent / "pom.xml"
NS = {"m": "http://maven.apache.org/POM/4.0.0"}

# A published coordinate: MAJOR.MINOR.PATCH, or a beta of one
# (MAJOR.MINOR.PATCH-beta.N, the org beta scheme of 2026-10-21; -rc.N is reserved). Never a
# SNAPSHOT, a range, LATEST/RELEASE or a property reference.
RELEASED = r"^\d+\.\d+\.\d+(-(beta|rc)\.[1-9]\d*)?$"


def _root():
    return ET.parse(POM).getroot()


def _managed(artifact_id):
    found = _root().findall(
        "m:dependencyManagement/m:dependencies/m:dependency", NS
    )
    return [
        d for d in found
        if d.findtext("m:artifactId", namespaces=NS) == artifact_id
    ]


class AuthCoreManagedVersion(unittest.TestCase):
    def test_auth_core_is_managed_once_under_the_org_group(self):
        entries = _managed("hugmesh-auth-core")
        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0].findtext("m:groupId", namespaces=NS), "net.hugmesh"
        )

    def test_managed_version_comes_from_a_property(self):
        entry = _managed("hugmesh-auth-core")[0]
        self.assertEqual(
            entry.findtext("m:version", namespaces=NS),
            "${hugmesh-auth-core.version}",
        )

    def test_property_is_a_literal_released_version(self):
        value = _root().findtext(
            "m:properties/m:hugmesh-auth-core.version", namespaces=NS
        )
        self.assertIsNotNone(value)
        self.assertRegex(value, RELEASED)

    def test_auth_core_is_managed_only_not_a_dependency_of_the_parent(self):
        direct = _root().findall("m:dependencies/m:dependency", NS)
        names = [d.findtext("m:artifactId", namespaces=NS) for d in direct]
        self.assertNotIn("hugmesh-auth-core", names)


class PublishedVersions(unittest.TestCase):
    """The metapom's own version and the net.hugmesh versions it pins are
    coordinates a consumer resolves from a registry, so each must be a
    release or a beta, never a SNAPSHOT."""

    def test_own_version_is_a_release_or_a_beta(self):
        self.assertRegex(_root().findtext("m:version", namespaces=NS), RELEASED)

    def test_org_library_pins_are_releases_or_betas(self):
        for prop in (
            "hugmesh-build-config.version",
            "hugmesh-commons.version",
            "hugmesh-auth-core.version",
        ):
            with self.subTest(prop=prop):
                value = _root().findtext(f"m:properties/m:{prop}", namespaces=NS)
                self.assertIsNotNone(value)
                self.assertRegex(value, RELEASED)


class DescriptionMatchesVersion(unittest.TestCase):
    def test_description_names_no_version_other_than_the_pom_version(self):
        root = _root()
        version = root.findtext("m:version", namespaces=NS)
        description = root.findtext("m:description", namespaces=NS)
        named = re.findall(r"\b\d+\.\d+\.\d+\b", description)
        stale = [v for v in named if v != version and v not in (
            root.findtext("m:parent/m:version", namespaces=NS),
            root.findtext("m:properties/m:spring-cloud.version", namespaces=NS),
        )]
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
