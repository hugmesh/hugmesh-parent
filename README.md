# hugmesh-parent

The HugMesh ecosystem **metapom** (`packaging=pom`). It consolidates the shared
Spring Boot 4.0.7 / Spring Cloud 2025.1.2 / Java 25 reactive-BFF baseline so every
service repo inherits one audited set of starters, versions, plugins, and publishing
config instead of copying them.

## Coordinates

```
groupId:    net.hugmesh
artifactId: hugmesh-parent
version:    2.8.0
packaging:  pom
```

Itself a child of `org.springframework.boot:spring-boot-starter-parent:4.0.7`.

This is the **2.8.0 / Boot-4 line**. The legacy **1.0.0 / Spring Boot 3.5.5 line**
is no longer used: on `origin/main`, every repo that parents off `hugmesh-parent` pins
2.8.0.

## What it provides

- **Properties:** `java.version=25`, UTF-8 encoding, and pinned versions for
  `hugmesh-commons` (2.1.0), the Spring Cloud release train (2025.1.2), SpringDoc
  (3.0.3, the Boot-4 / Spring Framework 7 line), Resilience4j (2.4.0, the Boot-4
  starter line), and the AWS SDK BOM (2.28.3).
- **Common dependencies** (inherited by every reactive BFF): WebFlux, Actuator,
  Security, OAuth2 Resource Server, Validation, Data-R2DBC + r2dbc-postgresql (runtime scope),
  Liquibase (+ `spring-boot-liquibase` runtime module — Boot 4 split
  `LiquibaseAutoConfiguration` out of the core autoconfigure umbrella, so without it
  migrations silently never run), spring-jdbc, postgresql (runtime scope), SpringDoc
  WebFlux UI; plus the test stack (spring-boot-starter-test, reactor-test,
  spring-security-test, r2dbc-h2, h2, the Boot-4 split test-slice modules
  `spring-boot-webflux-test` / `spring-boot-data-r2dbc-test`, and the Testcontainers
  integration-test infra `spring-boot-testcontainers` + testcontainers-postgresql/testcontainers-junit-jupiter/testcontainers-r2dbc).
- **dependencyManagement:** the Spring Cloud `spring-cloud-dependencies` BOM (import),
  `hugmesh-commons`, `hugmesh-build-config` (the resource-only ruleset jar consumed
  by the analysis plugins below), AWS SDK BOM (import), Resilience4j
  (`resilience4j-spring-boot4` + `resilience4j-reactor`), SpringDoc, the
  Testcontainers BOM (import), plus deliberate **H2 pins** (`r2dbc-h2 1.0.0.RELEASE` /
  `h2 2.3.232`) that override Boot 4's managed versions, whose combination regressed
  parameter binding for the H2 `@DataR2dbcTest` slices — children declare all of these
  without a `<version>`.
- **pluginManagement:** compiler, surefire (with the Byte Buddy
  `-Dnet.bytebuddy.experimental=true` flag for newer JDKs), spring-boot-maven-plugin,
  native-maven-plugin (GraalVM).
- **Inherited static-analysis enforcement** (`<build><plugins>`, runs in every Java
  child, no-op on this pom parent): PMD, Checkstyle and SpotBugs+FindSecBugs wire the
  org's secure/clean-Java + reactive-readability conventions and **fail the build on
  violations** (`:check` goals; `failOnViolation=true` for PMD/Checkstyle,
  `failOnError=true` for SpotBugs). See the section below.
- **`aspectjweaver`** is included in the dependency set so that `@CircuitBreaker` and
  other Spring AOP annotations from Resilience4j wire automatically across all child
  repos without any per-repo AspectJ configuration.
- **distributionManagement:** the GitLab project Maven Package Registry. The manual
  GitHub Packages release (see Publishing) overrides it on the command line.

## Static-analysis enforcement (inherited, fail-mode)

Every Java repo that parents off this metapom automatically runs three analysers on
`verify` — the child declares nothing. The curated rulesets are NOT in this repo; they
ship in the resource-only **`net.hugmesh:hugmesh-build-config`** jar and are
referenced on each plugin's own classpath (PMD `/hugmesh/*.xml`, Checkstyle/SpotBugs
`hugmesh/*.xml`). That is the only mechanism by which a separate repo can see a
ruleset that physically lives elsewhere, and it gives curated rules + automatic
inheritance with one new artifact.

| Plugin | Conventions | Rules | Output |
|--------|-------------|-------|--------|
| `maven-pmd-plugin` | **A**, **B** | `FinalFieldCouldBeStatic`, `ImmutableField` | `target/pmd.xml` |
| `maven-checkstyle-plugin` | **F**, **G**, **H** | `VisibilityModifier`, `FinalClass`, `HideUtilityClassConstructor`, `MutableException`, `LambdaBodyLength` | `target/checkstyle-result.xml` |
| `spotbugs-maven-plugin` + FindSecBugs | **D**, **E** | `EI_EXPOSE_REP*`, `MS_EXPOSE_REP`, `MS_MUTABLE_*`, `MS_PKGPROTECT`, `MS_SHOULD_BE_FINAL`, `MS_CANNOT_BE_FINAL` (include-filtered) | `target/spotbugsXml.xml` |

Convention **C** (enum for fixed string sets) and the *defensive-copy fix* /
*lambda→method-ref* / *nesting* halves of D and H have no reliable low-noise static
rule, so they remain agent-pass conventions — by design, no rule is added that would
flag every lambda or every collection field.

**Fail-mode.** All three run in CHECK mode via the `:check` goal (`pmd:check`,
`checkstyle:check`, `spotbugs:check`), not the reporting-only goals (`pmd:pmd`,
`checkstyle:checkstyle`, `spotbugs:spotbugs`). A finding fails the build. PMD and
Checkstyle gate on `failOnViolation=true`; **SpotBugs gates on `failOnError=true`**,
because `failOnViolation` is not a parameter of the `spotbugs:check` goal at all.

On `spotbugs:check`, `failOnError` gates real bug findings and SpotBugs-internal
analysis errors *together* (its failure message is `failed with <N> bugs and <M>
errors`); the plugin offers no way to separate them. An internal error therefore
fails the build by design — an incomplete analysis must not report green.

> **History — this gate was fail-open.** PR #6 moved SpotBugs to `spotbugs:check`
> and set `failOnViolation=true`, but that parameter does not exist on the goal
> (Maven only logs `[WARNING] Parameter 'failOnViolation' is unknown`) and left
> `failOnError=false` from the warn-first era. From `7d22f1a` until the flip to
> `failOnError=true`, **SpotBugs never failed any build in any child repo.** The
> claim that "the fleet was verified clean before each flip" is accurate for PMD
> (#4) and Checkstyle (#5), but was never true for SpotBugs (#6) — nothing was
> gating it.

**Scope.** Through build-config 0.3.0 the include filter listed only the
core-SpotBugs D/E patterns, and FindSecBugs 1.14.0's 144 patterns
(`SQL_INJECTION_*`, `COMMAND_INJECTION`, `HARD_CODE_PASSWORD`, …) share none of the
`EI_EXPOSE_REP*`/`MS_*` names, so the loaded FindSecBugs plugin contributed **zero**
findings — the gate enforced defensive-copy / mutable-static conventions only.
Build-config 0.4.0 (pinned here as `hugmesh-build-config` **0.5.0** post-rebrand)
re-scoped the include filter to admit the 137 FindSecBugs patterns empirically
measured to fire zero findings fleet-wide (SQLi, path-traversal, hard-coded
secrets, weak crypto, XXE, unsafe deserialization, SSRF, …), so the gate now
**does** enforce those security conventions on all future code, at zero cost
today. The 7 patterns that do fire fleet-wide (`SPRING_ENDPOINT`,
`CRLF_INJECTION_LOGS`, `IMPROPER_UNICODE` + 4 triaged FPs) remain excluded on
purpose; admitting them is tracked separately in `hugmesh-build-config`.

`hugmesh/spotbugs-exclude.xml` is the entity/test/Spring-injection baseline.
Through build-config 0.3.0 its Spring-injection suppression matched *layer*
package names (`.controller`/`.service`/…) while the BFF fleet uses *feature*
packages (`adminbff.announcement.AnnouncementService`), so it never fired — the
dominant reason live violation counts were high. Build-config 0.4.0 (pinned here
as 0.5.0) switched the match to the class-name **suffix** instead, so the
suppression fires for Spring constructor injection while still reporting
genuinely mutable state (`byte[]`/`char[]` key material,
`List`/`Map`/`Set`/`Collection`/`Date`) even inside a `*Service`.

**Escape hatch.** `-Dhugmesh.analysis.skip=true` skips all three (e.g. a fast
inner-loop build); default is `false`, so CI always runs them. To bump a ruleset, edit
`hugmesh-build-config` and bump `${hugmesh-build-config.version}` here — no runtime
artifact churn.

## Architecture

This repo has no runtime of its own — it is a POM artifact that sits between the
Spring Boot parent and every reactive-BFF child repo, plus the CI job that publishes it:

```mermaid
flowchart TD
    SBSP["spring-boot-starter-parent<br/>4.0.7"] --> SP["hugmesh-parent 2.8.0<br/>(this repo, packaging=pom)"]

    SBC["hugmesh-build-config<br/>(PMD / Checkstyle / SpotBugs rulesets)"] -.->|"plugin classpath only,<br/>not a compile dependency"| SP
    SC["hugmesh-commons 2.1.0"] -.->|"managed version"| SP

    SP -->|"parent + inherited starters,<br/>test infra, analysis plugins"| BFF["Reactive BFF child repos<br/>(admin-bff-api, user-bff-api, mod-bff-api,<br/>federation-api, forum-bff-api, wiki-bff-api, ...)"]

    SP -->|"./mvnw deploy<br/>-s settings.xml"| REG[("GitLab Maven<br/>Package Registry")]
    SP -.->|"manual Release workflow<br/>(release.yml)"| GHP[("GitHub Packages")]
    REG -->|"resolved via CI_JOB_TOKEN<br/>or local ~/.m2 install"| BFF
```

Two dotted inputs feed the parent without becoming a child's compile dependency:
`hugmesh-build-config` is read off each analysis plugin's own classpath (see the
table above), and `hugmesh-commons`'s version is only *managed* here — a child still
declares it explicitly to pull it in. The solid arrows are the real dependency/publish
paths: `spring-boot-starter-parent` down into this pom, this pom down into every child
BFF's effective POM, and the GitLab CI `deploy` stage publishing this artifact for
those children to resolve. The dotted arrow to GitHub Packages is the manual
`release.yml` workflow.

## Using it in a service repo

```xml
<parent>
  <groupId>net.hugmesh</groupId>
  <artifactId>hugmesh-parent</artifactId>
  <version>2.8.0</version>
  <relativePath/>
</parent>
```

Then remove from the child pom: `java.version`, the common dependency declarations,
and the common test dependencies. Keep only repo-specific dependencies (kafka, sshj,
cassandra, icu4j, webauthn4j, s3, …), repo-specific properties, and any custom plugin
configuration.

The **gateway** (`hugmesh-gateway`) is on the same baseline this metapom targets
(Spring Boot 4.0.7, Spring Cloud 2025.1.2, Java 25) but does not parent off it: its
`pom.xml` names `spring-boot-starter-parent` directly, because this metapom is
BFF-focused and would pull Liquibase, Testcontainers and R2DBC-Postgres onto a
Cassandra-based gateway.

## What stays per-repo

Repo-specific dependencies are never pulled into the parent. See each service's pom.

## Publishing

`.gitlab-ci.yml` has two jobs. `validate:pom` runs `./mvnw validate` on every pipeline.
`deploy:maven` publishes the POM to the GitLab Maven Package Registry on the default
branch or on a tag, via `./mvnw -B -ntp -s settings.xml deploy`. Authentication uses the
GitLab-injected `CI_JOB_TOKEN` (a job-scoped, auto-expiring credential) read from
`settings.xml` — **no secret is committed**.

`.github/workflows/release.yml` is a second, **manual** route
(`workflow_dispatch` only): it publishes the POM to GitHub Packages with
`-s .github/maven-ci-settings.xml`. It is link 2 of 4 in the publish chain
`hugmesh-build-config` 0.5.0 → `hugmesh-parent` 2.8.0 → `hugmesh-commons` 2.1.0 →
`hugmesh-auth-core` 2.5.1; see `RELEASING.md`.

For local development, `./mvnw install` writes the POM to `~/.m2` so sibling repos on
the same machine can resolve it offline.

## Current State

- On `main`, the metapom is fully on the **2.8.0 / Boot-4** baseline: Spring Boot
  4.0.7, Spring Cloud 2025.1.2, Java 25, `hugmesh-commons` 2.1.0. On
  `hugmesh/hugmesh-parent` the merged PRs are #1, #3, #5, #6 and #7 (the last
  old-brand spellings, the CI-only GitHub Packages route, and the
  `PACKAGES_READ_TOKEN` release docs and preflight); older PR numbers in the git
  history belong to the repo's earlier home. The remote
  branches that still exist are all merged; there is no active feature branch.
- The manual Release workflow has run once on this repo (2026-10-07, run 37699571478)
  and failed at its preflight step: HTTP 404 reading `hugmesh-build-config` from
  GitHub Packages, with `PACKAGES_READ_TOKEN` unset. Nothing has been published
  through it.
- This metapom carries **no application/auth code** — it only pins versions, shared
  starters, plugins, and publishing config. The org's shared security/tenancy code
  lives in `hugmesh-commons` (`net.hugmesh.commons.*`, its own release line
  is currently 2.1.0 — the same version this metapom pins in `dependencyManagement`),
  and the shared account/session/MFA/Casdoor-admin infrastructure lives in
  `hugmesh-auth-core` (own release line currently 2.5.1, depends on commons and on
  this parent 2.8.0; consumed by `user-bff` and `admin-bff`). Both are downstream
  consumers of this baseline (they parent off 2.8.0), not part of it — don't confuse
  their own artifact version with the 2.8.0 parent version they depend on.
- Ecosystem auth model (for context; enforced in the consumer repos, not here):
  Casdoor is the SSO IdP. `login-ui` renders a native username/password (+MFA) form
  and POSTs it to `/bff/login`; `user-bff` runs the PKCE/state handshake and the
  internal Casdoor login and code→token exchange server-side, and holds the
  per-session JWT custody/refresh. The browser is never redirected to Casdoor and only
  ever holds an **opaque `bff_`-prefixed session** — the user never sees their Casdoor
  JWT. The gateway is a Casdoor-JWT OAuth2 resource server. It accepts the `bff_`
  session through an introspection filter (on by default) and, optionally, an exchange
  filter that swaps `bff_` for the internal custody JWT (off by default). Authorization
  is data-driven by the `gateway_route_access` Postgres table. Login/session/account
  logic is being relocated from `admin-bff` to `user-bff` (account/session **data**
  stays in `admin-bff-db`, reached over mTLS + `X-Internal-Token`).
- The Spring Cloud Gateway 5.0 route-config move
  (`spring.cloud.gateway.routes` → `spring.cloud.gateway.server.webflux.routes`) is a
  gateway/generator concern, not a metapom concern; this repo only pins the Spring
  Cloud 2025.1.2 train that introduces it.

## Roadmap

This repo is intentionally thin; its roadmap is to **track the org baseline** as the
platform evolves:

- Keep the 2.8.0 line pinned to the same Spring Boot / Spring Cloud train the
  gateways run, and bump shared versions (`hugmesh-commons`, SpringDoc,
  Resilience4j, Testcontainers, AWS SDK) in lockstep across consumers.
- Add `hugmesh-auth-core` to `dependencyManagement` (managed version) once enough
  consumers depend on it, so `user-bff` / `admin-bff` declare it without a `<version>`.
- Retire the H2 pins if/when an upstream Boot-4 r2dbc-h2 release fixes the
  parameter-binding regression.
- Publish through GitLab CI (`CI_JOB_TOKEN`) and, once the repos can read each other's
  packages, through the manual GitHub Packages Release workflow.

## Known Gaps / TODO

- `pom.xml:23`, the `<description>`, still reads `"HugMesh ecosystem metapom (2.7.0 /
  Boot-4 line)"` while `<version>` (`pom.xml:20`) is 2.8.0. This free-text field has
  drifted from `<version>` twice. It is a one-line `pom.xml` fix, left out of this
  docs-only change.
- The Release workflow has no automated guard. It is `workflow_dispatch` only; nothing
  but review stops it gaining a `push` trigger that would republish an
  already-published, immutable coordinate (`RELEASING.md`).
- The metapom has no Java sources, so there is no code or test of its own to check
  beyond `./mvnw validate`.
