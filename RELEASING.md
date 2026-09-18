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
