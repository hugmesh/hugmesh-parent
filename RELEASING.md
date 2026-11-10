# Releasing hugmesh-parent

`net.hugmesh:hugmesh-parent` is **link 2 of 4** in the org's Maven publish chain:

```
hugmesh-build-config 0.6.0-beta.1  ->  hugmesh-parent 2.9.0-beta.1  ->  hugmesh-commons 2.2.0-beta.1  ->  hugmesh-auth-core 2.6.0-beta.1
```

## How a version is published (beta scheme, 2026-10-21)

The version is **`2.9.0-beta.1`**: the org beta scheme (`MAJOR.MINOR.PATCH-beta.N`). 2.8.0 was
pinned by every BFF, so the beta goes on the next minor line. N starts at 1 and goes up by
one for each further beta of 2.9.0. Never a SNAPSHOT, never `+build` metadata.

`.github/workflows/release.yml` publishes **only when a person pushes a tag** `v<version>`
that equals `<version>` in `pom.xml`: a beta `vX.Y.Z-beta.N` on a commit on `main`, a stable
`vX.Y.Z` on a commit on `release/X.Y` ("Release channels" below):

| Event | What runs |
|---|---|
| push of tag `vX.Y.Z-beta.N` (commit on `main`) | version guard, repository checks, `verify`, `deploy` to GitHub Packages, then a GitHub Release marked prerelease and not latest |
| push of tag `vX.Y.Z` (commit on `release/X.Y`) | the same, then a full GitHub Release, Latest only on the newest stable line |
| `workflow_dispatch` on a `v*` tag | the same as its push; this is the re-run path (an existing GitHub Release is left alone) |
| push to `release/X.Y`, `workflow_dispatch` on `main` or `release/X.Y` | version guard, repository checks, `verify` only; nothing is deployed |
| anything else | the version job refuses |

There is no push trigger on `main` and no `pull_request` trigger: a Maven coordinate is
immutable, so publish-on-merge would try to redeploy the same version.
`scripts/test_release_workflow.py` and `scripts/test-release-channel.sh` pin that shape (and
both run inside the workflow).

**Before the tag:** `hugmesh-build-config` `v0.6.0-beta.1` must already be published. The
analyser plugins load its ruleset jar during `verify`. Measured on 2026-10-21, offline, with
that jar absent from the local repository:

```
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-pmd-plugin:3.28.0:pmd (pmd) on project hugmesh-parent:
  ... the artifact net.hugmesh:hugmesh-build-config:jar:0.6.0-beta.1 has not been downloaded from it before.
```

The `hugmesh-commons` and `hugmesh-auth-core` versions are `dependencyManagement` entries
only. A `pom`-packaged parent does not resolve them, so they publish after this link.

**Where it runs.** Every job's `runs-on` uses the repository variable `RUNS_ON_PUBLISH` (a
JSON array such as `["self-hosted","Linux","X64"]`) for a non-PR event on `main` or a `v*`
tag, and hosted `ubuntu-latest` otherwise, including when the variable is unset. Deleting
`RUNS_ON_PUBLISH` sends publishing back to hosted runners. On the self-hosted runner the
build uses a fresh local Maven repository under the job's temp directory, so a
`net.hugmesh` artifact that was only installed locally can never satisfy `verify`.

**To publish by hand** (the org release script below does this for you):

```
git tag -a v<version> -m "hugmesh-parent <version>" <commit on main, or on release/X.Y for a stable>
git push origin v<version>
```

Re-run on the same tag: `gh workflow run release.yml --repo hugmesh/hugmesh-parent --ref v<version>`.

## Release channels: beta from `main`, stable from `release/X.Y`

The tag decides the channel. `.github/workflows/release.yml` carries the marker
`hugmesh-release-channels: beta+stable` that the org release script looks for;
`scripts/release-channel.sh` holds the branch rules, and `scripts/test-release-channel.sh`
tests them, the workflow's own version guard and its `gh release create` step. The version
job runs that test first, so a broken rule fails the run before anything is built.

| Ref | Channel | What the run does |
|---|---|---|
| tag `vX.Y.Z-beta.N`, commit on `main` | beta | verify, deploy, sign, GitHub Release marked prerelease, never Latest |
| tag `vX.Y.Z`, commit on `release/X.Y` | stable | verify, deploy, sign, full GitHub Release, marked Latest only when `X.Y` is the newest stable line (decided again right before the Release is created, so a re-run never marks an older line Latest) |
| push to `release/X.Y` | none | `verify` only, nothing deployed; `pom.xml` must be `X.Y.*`. The org release script requires this run to be green before it tags `release/X.Y` |
| `workflow_dispatch` on `main` or `release/X.Y` | none | `verify` only |
| `workflow_dispatch` on a `v*` tag | as the tag | the re-run path; an existing GitHub Release is left alone |
| anything else | refused | an `-rc.N` tag, a beta tag off `main`, a stable tag off its own `release/X.Y`, a stable older than a published `vX.Y.W`, a branch not named `release/X.Y`, a tag that is not `v` + the pom version |

There is still no push trigger on `main` and no `pull_request` trigger. A `release/X.Y`
push only verifies: every deploy, signing and GitHub Release step is gated on
`kind == 'release'`, which only a matching `v*` tag gets. A published coordinate is
immutable, so a stable fix goes out as the next patch, never over an existing version.
A `release/X.Y` run always lands on hosted `ubuntu-latest`: the `RUNS_ON_PUBLISH`
expression names only `main` and `v*` tags.

### One command

Releases are driven from `hugmesh-generator` (`docs/RELEASING.md` there). It reads this
repo's version from `pom.xml` (its row in `scripts/release/repos.tsv`), so no version is
typed for a beta or a stable cut. Every command below is a dry run until `--apply` is added.

```
scripts/release.sh                                   # beta: tag main's X.Y.Z-beta.N, whole org
scripts/release.sh --only hugmesh-parent                # beta of this repo only
scripts/release.sh --channel stable                  # stable cut: release/X.Y from main, X.Y.Z there
scripts/release.sh --channel stable --version X.Y.Z --only hugmesh-parent
                                                     # a patch on the existing release/X.Y
```

A new minor needs no edit to the workflow or the tests: bump `<version>` in `pom.xml` in a
PR (the tests derive their fixture versions from it), merge, then run the command. A patch
is: cherry-pick the fix onto `release/X.Y`, then the `--version X.Y.(Z+1)` command, which
opens the version-bump PR into `release/X.Y`, waits for its green push run, and tags.

The full story — why the chain exists, what a release IS in this org, and what the operator
clicks on launch day — is in **`hugmesh-auth-core/RELEASING.md`**. This file is only what is
specific to the metapom. Written 2026-09-17 against operator decision 27
(hugmesh-generator#347): *"B for the mechanism, A prepared"* — source-building stays the
mechanism, the publish path is made real but unfired.

## What this repo needs to resolve, and from where

Its own `<parent>` is `org.springframework.boot:spring-boot-starter-parent:4.0.7`, which is
on Maven Central. The one `net.hugmesh` artifact it needs is
**`net.hugmesh:hugmesh-build-config:0.6.0-beta.1`**, and it needs it on a **plugin** classpath, not
as a project dependency: `pom.xml`'s `maven-pmd-plugin`, `maven-checkstyle-plugin` and
`spotbugs-maven-plugin` blocks each list it under the plugin's own `<dependencies>` so the
analyser reads the curated ruleset off its plugin classloader.

That matters because **Maven resolves a plugin's dependencies from the plugin
repositories**, and those three executions are bound to `verify`, which runs before
`install`/`deploy` **even for `pom` packaging**. A settings file that declared only
`<repositories>` would resolve nothing this build needs and would fail at `verify`, on the
ruleset jar, looking like an analyser problem.

So `.github/maven-ci-settings.xml` declares `hugmesh-build-config` under **both**
`<repositories>` and `<pluginRepositories>`.

## Why the repository URL is in a CI-only settings file and not in pom.xml

`maven.pkg.github.com` requires authentication even to **read**. Measured 2026-09-17:

```
$ curl -s -o /dev/null -w '%{http_code}\n' \
    https://maven.pkg.github.com/hugmesh/hugmesh-build-config/net/hugmesh/hugmesh-build-config/0.5.0/hugmesh-build-config-0.5.0.pom
401
$ curl ... -H "Authorization: Bearer $(gh auth token)" <same URL>
401     # classic token; scopes gist/project/read:org/repo/workflow — no read:packages
```

This pom is the parent of **every Java repo in the org**. A `<repositories>` entry here
would make every unauthenticated build in the fleet fail: a developer's `./mvnw verify`, and
`hugmesh-generator/tests/stack/m2-bootstrap.sh`, which is how the compose lane builds these
libraries today and which decision 27 deliberately keeps as the mechanism. The settings file
is passed with `-s` by `release.yml` and by nothing else, so it reaches CI and nobody else.

`-s` also *replaces* the user settings file, which is why the file carries a
`<server><id>github</id>` of its own: without it the deploy step's
`-DaltDeploymentRepository=github::default::…` would upload with no credential, because the
entry `actions/setup-java` generates into `~/.m2/settings.xml` is no longer being read.

## Cross-repo package reads — the grant that going public does NOT perform

This repo's release build resolves `net.hugmesh` artifacts published from **other**
repositories (`hugmesh-build-config`, which this metapom puts on the PMD/Checkstyle/SpotBugs plugin classpaths). `secrets.GITHUB_TOKEN` is scoped to the repository whose
workflow is running, and GitHub does not extend it across repositories for package reads:
the build must present a token carrying `read:packages`. That token is the secret
**`PACKAGES_READ_TOKEN`** (operator decision 90a = B, hugmesh-generator#347, answered
2026-09-23).

The first cut of this round wired every upstream `<server>` to `${env.GITHUB_TOKEN}`, and
what makes that worse than an ordinary missing step is the **shape of its failure**. Maven
reports it as `Could not resolve net.hugmesh:...`, which is the same string this file and
the workflow comments teach a reader to read as *"the upstream is not published yet"*. The
natural response — re-publish the upstream — burns a version, succeeds, and hits the same
wall. So:

- **The read credential is its own env var.** `.github/maven-ci-settings.xml` authenticates
  the `github-hugmesh-*` upstream servers with `${env.UPSTREAM_PACKAGES_*}`, injected by
  `release.yml` as `${{ secrets.PACKAGES_READ_TOKEN || secrets.GITHUB_TOKEN }}`. The
  `github` **deploy** server keeps the automatic `${env.GITHUB_TOKEN}` — a workflow may
  always write packages for its own repository, so the deploy half needs no operator secret.
- **A preflight step names the failure correctly.** Before maven runs, `release.yml` probes
  each upstream's `maven-metadata.xml` with the exact credential maven will use, and tells
  `401`/`403` (*cannot authenticate; NOT "unpublished"*) apart from `404` (*nothing published
  there yet, **or** published and invisible to this credential — GitHub masks an unauthorised
  read of a private package as 404*). Exercised against the live registry on 2026-09-18 with
  an invalid credential: it emitted the `401` branch for every upstream and exited 1.

**Neither of those grants anything.** The grant is the **`PACKAGES_READ_TOKEN`**
secret. **Decided 2026-09-23, decision 90a = B:** one **classic** personal access token with
the `read:packages` scope, stored as the secret `PACKAGES_READ_TOKEN`, separate from
`RELEASE_CHAIN_TOKEN`, created by the operator and **kept** as a standing secret, not a
launch-day stopgap to be retired afterwards. Scope: a REPOSITORY secret on each repo whose `release.yml` reads it (`hugmesh-parent`, `hugmesh-commons`, `hugmesh-auth-core`), because the org is on the Free plan and the repos are private, and an org secret is understood not to reach private repos on that plan (from GitHub's plan limits, untested; see `hugmesh-auth-core/RELEASING.md` §6.2 "Secret scope"). It must be classic: GitHub's docs say *"GitHub
Packages only supports authentication using a personal access token (classic)"* (read from
the docs, not tested). It does not depend on any package existing first, so it serves a cold
first publish. `release.yml` already prefers it and falls back to `GITHUB_TOKEN` only when it
is absent; that fallback is **not a route**, because it cannot read another repository's
packages (above).

- *Not the plan:* per-package **Manage Actions access** grants ("route A", which this file
  offered as an option before 2026-09-23: on each upstream package, add this repository).
  GitHub's docs list that setting only for container, npm, NuGet and RubyGems packages and
  say Maven packages inherit their repository's permissions, so it is probably not offered
  for these Maven packages at all. That is read from the docs, not tested, because no
  `net.hugmesh` package is known to have been published. Even where it exists it can only be
  granted after a package is published, so it could never serve a first run. Where a
  `release.yml` comment or preflight message in this repo still offers it, that text predates
  decision 90a.

Full click list: `hugmesh-auth-core/RELEASING.md` §6.2. **Nothing here has been executed** —
no Actions job in this org starts at all today (billing; `hugmesh-auth-core/RELEASING.md`
§6.1), and no `PACKAGES_READ_TOKEN` exists (measured 2026-10-07: `gh api repos/hugmesh/<repo>/actions/secrets` and `.../actions/organization-secrets` both answer 200 with `total_count` 0, so `PACKAGES_READ_TOKEN` is absent, not merely inferred; the org-level listing `/orgs/hugmesh/actions/secrets` still answers 403).

## Changed on 2026-09-17

- `.github/maven-ci-settings.xml` added (CI-only; the whole resolution route).
- `.github/workflows/release.yml`: the deploy step passes `-s .github/maven-ci-settings.xml`.
- Runner JDK `21` → `25`. It was pinned to 21 on the reasoning that `pom` packaging does not
  compile. That is true of this project's (absent) sources but not of the toolchain the bound
  analyser plugins load, and a metapom that publishes a Java 25 baseline from a Java 21
  runner was a discrepancy nobody had verified either way. **Still unverified** — see below.

Measured on this branch, offline, so nothing from the network can contribute:

```
$ ./mvnw -o -q -B -ntp -N help:evaluate -Dexpression=project.pluginRepositories -DforceStdout
    <id>central</id>                        # unchanged for every normal build
$ ./mvnw -o -q -B -ntp -N -s .github/maven-ci-settings.xml help:evaluate -Dexpression=project.pluginRepositories -DforceStdout
    <id>github-hugmesh-build-config</id>
    <id>central</id>
```

## What a human must still verify

- **This workflow has run once** (2026-10-07, run 37699571478, the earlier dispatch-only
  shape). It stopped at the preflight: HTTP 404 reading `hugmesh-build-config`, with
  `PACKAGES_READ_TOKEN` unset. The tag-driven shape of 2026-10-21 has never run.
- **Hosted Actions jobs in this org do not start while the repos are private.** The annotation on
  the most recent runs across the org is *"The job was not started because recent account
  payments have failed or your spending limit needs to be increased."* Private-repo Actions
  minutes are billed; public-repo minutes are free, so this dissolves when the repos go
  public. `hugmesh-auth-core/RELEASING.md` §6.1 has the exact `gh api` calls.
- **The release workflow's shape is pinned by `scripts/test_release_workflow.py`** (since
  2026-10-21): only `push` of `v*` tags and `workflow_dispatch`, no branch or
  `pull_request` trigger, the publish runner line on every job, `deploy` only on a release
  run, the tag-equals-version and tag-on-main checks, a prerelease that is never latest.
  It runs locally with `python3 -m unittest discover -s scripts` and as a step of the
  workflow's `version` job. It is a text check, so it cannot prove the workflow runs.
- **Whether anything is already published is unknown, not "nothing".** Confirming needs a
  token with `read:packages`; this box's has none
  (`gh api /orgs/hugmesh/packages?package_type=maven` → HTTP 403).
