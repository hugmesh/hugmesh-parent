"""Shape checks on .github/workflows/release.yml.

This repo is pom packaging, so it has no JUnit phase that could pin its own release
workflow the way hugmesh-commons and hugmesh-auth-core do. These checks are that pin.
They read the file as text (no YAML library is needed on any runner).

Run: python3 -m unittest discover -s scripts
"""
import pathlib
import re
import unittest

WORKFLOW = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".github" / "workflows" / "release.yml"
)

# The org's publish runner line (beta scheme, 2026-10-21, section 3.1). The local
# runner is chosen only for a non-PR event on main or on a v*/studio-v* tag, and only
# when the RUNS_ON_PUBLISH variable is set; everything else is hosted ubuntu-latest.
RUNS_ON_PUBLISH_LINE = (
    "runs-on: ${{ fromJSON(github.event_name != 'pull_request' && "
    "github.event_name != 'pull_request_target' && "
    "(github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v') || "
    "startsWith(github.ref, 'refs/tags/studio-v')) && vars.RUNS_ON_PUBLISH || "
    "'\"ubuntu-latest\"') }}"
)


def _lines():
    return WORKFLOW.read_text(encoding="utf-8").splitlines()


def _code(lines):
    """Lines that are not blank and not YAML comments."""
    return [ln for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _block(lines, header):
    """The lines under the first line matching `header` (a regex on the stripped
    line), up to the next code line indented at or left of the header."""
    code = _code(lines)
    for i, line in enumerate(code):
        if re.fullmatch(header, line.strip()):
            depth = _indent(line)
            out = []
            for nxt in code[i + 1:]:
                if _indent(nxt) <= depth:
                    break
                out.append(nxt)
            return out
    raise AssertionError(f"no line matching {header!r} in {WORKFLOW}")


def _jobs(lines):
    """{job id: its lines} for every job under the top-level `jobs:` key."""
    body = _block(lines, r"jobs:")
    depth = min(_indent(ln) for ln in body)
    jobs, current = {}, None
    for line in body:
        if _indent(line) == depth:
            current = line.strip().rstrip(":")
            jobs[current] = []
        else:
            jobs[current].append(line)
    return jobs


def _steps_of(job_lines):
    """Split a job's lines into steps (each starting at a `- ` list item)."""
    steps, current, depth = [], None, None
    for line in job_lines:
        stripped = line.strip()
        if stripped.startswith("- ") and (depth is None or _indent(line) == depth):
            depth = _indent(line)
            current = [line]
            steps.append(current)
        elif current is not None and _indent(line) > (depth or 0):
            current.append(line)
    return steps


class Triggers(unittest.TestCase):
    def setUp(self):
        self.on = [ln.strip() for ln in _block(_lines(), r"on:")]

    def test_only_tag_pushes_and_manual_dispatch(self):
        keys = [ln.rstrip(":").split(":")[0] for ln in self.on
                if not ln.startswith(("tags", "-", "branches", "paths"))]
        self.assertEqual(sorted(keys), ["push", "workflow_dispatch"])

    def test_push_is_tags_v_only_never_a_branch(self):
        self.assertIn("tags: ['v*']", self.on)
        for line in self.on:
            self.assertFalse(line.startswith("branches"), line)

    def test_no_pull_request_trigger(self):
        text = "\n".join(self.on)
        self.assertNotIn("pull_request", text)


class Runners(unittest.TestCase):
    def test_every_job_uses_the_publish_runner_line(self):
        jobs = _jobs(_lines())
        self.assertGreaterEqual(len(jobs), 3)
        for name, body in jobs.items():
            with self.subTest(job=name):
                runs_on = [ln.strip() for ln in body
                           if ln.strip().startswith("runs-on:")]
                self.assertEqual(runs_on, [RUNS_ON_PUBLISH_LINE])

    def test_nothing_reads_the_old_runs_on_variable(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"vars\.RUNS_ON(?!_PUBLISH)", text))


class Publishing(unittest.TestCase):
    def setUp(self):
        self.jobs = _jobs(_lines())

    def test_version_guard_ties_the_tag_to_the_pom_and_to_main(self):
        text = "\n".join(self.jobs["version"])
        self.assertIn('"${GITHUB_REF_NAME#v}" != "$version"', text)
        self.assertIn("git merge-base --is-ancestor HEAD origin/main", text)
        self.assertIn("*-SNAPSHOT)", text)
        self.assertIn("kind=release", text)
        self.assertIn("kind=main", text)

    def test_deploy_runs_only_on_a_release_run(self):
        deploys = [s for s in _steps_of(self.jobs["publish"])
                   if any(" deploy " in ln for ln in s if "./mvnw" in ln)]
        self.assertEqual(len(deploys), 1)
        conditions = [ln.strip() for ln in deploys[0]
                      if ln.strip().startswith("if:")]
        self.assertEqual(
            conditions, ["if: needs.version.outputs.kind == 'release'"]
        )

    def test_every_maven_call_uses_the_ci_settings_and_a_private_repo(self):
        calls = [ln for ln in self.jobs["publish"] if "./mvnw" in ln]
        self.assertGreaterEqual(len(calls), 2)
        for line in calls:
            with self.subTest(line=line.strip()):
                self.assertIn("-s .github/maven-ci-settings.xml", line)
                self.assertIn('-Dmaven.repo.local="$MAVEN_REPO_LOCAL"', line)

    def test_github_release_is_a_prerelease_never_latest_for_a_beta(self):
        body = self.jobs["github-release"]
        text = "\n".join(body)
        self.assertIn("if: needs.version.outputs.kind == 'release'",
                      [ln.strip() for ln in body])
        self.assertIn("flags+=(--prerelease --latest=false)", text)
        self.assertIn("--verify-tag", text)


if __name__ == "__main__":
    unittest.main()
