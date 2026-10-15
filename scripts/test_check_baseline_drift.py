"""Tests for check_baseline_drift.py. Run: python3 -m unittest discover -s scripts"""
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path

import check_baseline_drift as cbd

REPO_POM = Path(__file__).resolve().parent.parent / "pom.xml"


def pom(parent, version=None, props=None, commons=None):
    group, artifact, pver = parent
    props_xml = "".join(f"<{k}>{v}</{k}>" for k, v in (props or {}).items())
    own = f"<version>{version}</version>" if version else ""
    dep = (
        "<dependencies><dependency><groupId>net.hugmesh</groupId>"
        f"<artifactId>hugmesh-commons</artifactId><version>{commons}</version>"
        "</dependency></dependencies>" if commons else ""
    )
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0">'
        f"<parent><groupId>{group}</groupId><artifactId>{artifact}</artifactId>"
        f"<version>{pver}</version></parent>{own}"
        f"<properties>{props_xml}</properties>{dep}</project>"
    )


BOOT = ("org.springframework.boot", "spring-boot-starter-parent")
META = ("net.hugmesh", "hugmesh-parent")
BASE_PROPS = {"spring-cloud.version": "2025.1.2", "springdoc.version": "3.0.3",
              "hugmesh-commons.version": "2.1.0"}


def base():
    return cbd.parse(pom(BOOT + ("4.0.7",), "2.8.0", BASE_PROPS))


class CompareTest(unittest.TestCase):
    def test_aligned_consumers_are_clean(self):
        drift, notes = cbd.compare(base(), {
            "gw": pom(BOOT + ("4.0.7",), props={"spring-cloud.version": "2025.1.2"}),
            "bff": pom(META + ("2.8.0",)),
        })
        self.assertEqual((drift, notes), ([], []))

    def test_boot_drift(self):
        drift, _ = cbd.compare(base(), {"gw": pom(BOOT + ("4.0.6",))})
        self.assertEqual(len(drift), 1)
        self.assertIn("gw: Spring Boot 4.0.6", drift[0])

    def test_spring_cloud_drift(self):
        drift, _ = cbd.compare(base(), {
            "gw": pom(BOOT + ("4.0.7",), props={"spring-cloud.version": "2025.1.1"})})
        self.assertEqual(len(drift), 1)
        self.assertIn("spring-cloud.version 2025.1.1", drift[0])

    def test_metapom_version_drift(self):
        drift, _ = cbd.compare(base(), {"bff": pom(META + ("2.7.0",))})
        self.assertEqual(len(drift), 1)
        self.assertIn("hugmesh-parent 2.7.0", drift[0])

    def test_shared_pin_disagreement_is_a_note_not_drift(self):
        drift, notes = cbd.compare(base(), {
            "bff": pom(META + ("2.8.0",), props={"springdoc.version": "3.0.0"},
                       commons="2.0.0")})
        self.assertEqual(drift, [])
        self.assertEqual(len(notes), 2)
        self.assertTrue(any("springdoc.version 3.0.0" in n for n in notes))
        self.assertTrue(any("hugmesh-commons dependency 2.0.0" in n for n in notes))

    def test_property_reference_is_not_a_literal_pin(self):
        drift, notes = cbd.compare(base(), {
            "bff": pom(META + ("2.8.0",), commons="${hugmesh-commons.version}")})
        self.assertEqual((drift, notes), ([], []))

    def test_missing_pom_is_noted(self):
        drift, notes = cbd.compare(base(), {"nginx": None})
        self.assertEqual(drift, [])
        self.assertIn("nginx: no pom.xml", notes[0])

    def test_real_pom_parses(self):
        facts = cbd.parse(REPO_POM.read_text(encoding="utf-8"))
        self.assertEqual(facts["parent_key"], BOOT)
        self.assertRegex(facts["parent_version"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(facts["props"]["spring-cloud.version"], r"^\d{4}\.\d+\.\d+$")


class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.metapom = self.root / "metapom.xml"
        self.metapom.write_text(pom(BOOT + ("4.0.7",), "2.8.0", BASE_PROPS))

    def repo(self, name, pom_xml=None, branch="main"):
        d = self.root / name
        d.mkdir()
        git = ["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(git + ["init", "-q", "-b", branch], check=True)
        if pom_xml is not None:
            (d / "pom.xml").write_text(pom_xml)
        else:
            (d / "README").write_text("x")
        subprocess.run(git + ["add", "."], check=True)
        subprocess.run(git + ["commit", "-q", "-m", "c"], check=True)

    def run_cli(self, *repos, ref="main"):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cbd.main(["--root", str(self.root), "--ref", ref,
                             "--pom", str(self.metapom), *repos])
        return code, out.getvalue(), err.getvalue()

    def test_clean_exits_zero(self):
        self.repo("gw", pom(BOOT + ("4.0.7",)))
        self.repo("web")
        code, out, _ = self.run_cli("gw", "web")
        self.assertEqual(code, 0)
        self.assertIn("ok: 1 consumers on Boot 4.0.7", out)

    def test_drift_exits_one(self):
        self.repo("gw", pom(BOOT + ("4.0.6",)))
        code, out, _ = self.run_cli("gw")
        self.assertEqual(code, 1)
        self.assertIn("DRIFT: gw: Spring Boot 4.0.6", out)

    def test_missing_checkout_is_not_clean(self):
        code, _, err = self.run_cli("absent")
        self.assertEqual(code, 2)
        self.assertIn("UNREADABLE", err)

    def test_missing_ref_is_not_clean(self):
        self.repo("gw", pom(BOOT + ("4.0.7",)))
        code, _, err = self.run_cli("gw", ref="origin/main")
        self.assertEqual(code, 2)
        self.assertIn("ref origin/main not found", err)

    def test_reads_the_ref_not_the_working_tree(self):
        self.repo("gw", pom(BOOT + ("4.0.7",)))
        (self.root / "gw" / "pom.xml").write_text(pom(BOOT + ("9.9.9",)))
        code, _, _ = self.run_cli("gw")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
