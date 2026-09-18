# Releasing hugmesh-parent

`net.hugmesh:hugmesh-parent` is **link 2 of 4** in the org's Maven publish chain:

```
hugmesh-build-config 0.5.0  ->  hugmesh-parent 2.8.0  ->  hugmesh-commons 2.1.0  ->  hugmesh-auth-core 2.5.1
```

The full story — why the chain exists, what a release IS in this org, and what the operator
clicks on launch day — is in **`hugmesh-auth-core/RELEASING.md`**. This file is only what is
specific to the metapom. Written 2026-09-17 against operator decision 27
(hugmesh-generator#347): *"B for the mechanism, A prepared"* — source-building stays the
mechanism, the publish path is made real but unfired.

## What this repo needs to resolve, and from where

Its own `<parent>` is `org.springframework.boot:spring-boot-starter-parent:4.0.7`, which is
on Maven Central. The one `net.hugmesh` artifact it needs is
**`net.hugmesh:hugmesh-build-config:0.5.0`**, and it needs it on a **plugin** classpath, not
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
each upstream package must name this repository under **Manage Actions access** in its own
package settings, or the build must present a token carrying `read:packages`.

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

**Neither of those grants anything.** On launch day the operator picks one of two routes,
and **that decision has not been made**:

- **Route A, no secret:** on each upstream package → *Package settings* → **Manage Actions
  access** → add this repository. Only possible **after** that package exists, so it cannot
  be set up ahead of a cold first publish.
- **Route B, one secret, works cold:** a PAT with `read:packages` on the hugmesh org stored
  as **`PACKAGES_READ_TOKEN`** (org secret, or a repo secret here). `release.yml` prefers it
  and falls back to `GITHUB_TOKEN`. This is the route for a launch-day single-click publish.

Full click list: `hugmesh-auth-core/RELEASING.md` §6.2. **Nothing here has been executed** —
no Actions job in this org starts at all today (billing; `hugmesh-auth-core/RELEASING.md`
§6.1), and no `PACKAGES_READ_TOKEN` exists (inferred — listing secrets needs org-admin and
answers 403 from this box).

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

- **This workflow has never run.** `gh run list --repo hugmesh/hugmesh-parent` → empty.
- **No Actions job in this org starts at all today**, so it could not have. The annotation on
  the most recent runs across the org is *"The job was not started because recent account
  payments have failed or your spending limit needs to be increased."* Private-repo Actions
  minutes are billed; public-repo minutes are free, so this dissolves when the repos go
  public. `hugmesh-auth-core/RELEASING.md` §6.1 has the exact `gh api` calls.
- **There is no automated guard on this file.** `hugmesh-auth-core` pins the shape of its own
  release workflow with `ReleaseMetadataGuardTest` (9 checks, mutation-tested). This repo is
  `pom` packaging: it has no `compile`/`test` phase and therefore cannot run a JUnit guard at
  all. The equivalent pin for this repo would have to live in `hugmesh-generator`'s shell
  suite, which is outside the file set this change was allowed to touch. **Until that exists,
  the only thing stopping this workflow gaining a `push` trigger is review.**
- **Whether anything is already published is unknown, not "nothing".** Confirming needs a
  token with `read:packages`; this box's has none
  (`gh api /orgs/hugmesh/packages?package_type=maven` → HTTP 403).
