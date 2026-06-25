# snapdragon-parent

The Snapdragon ecosystem **metapom** (`packaging=pom`). It consolidates the shared
Spring Boot 4.0.7 / Spring Cloud 2025.1 / Java 25 reactive-BFF baseline so every
service repo inherits one audited set of starters, versions, plugins, and publishing
config instead of copying them.

## Coordinates

```
groupId:    systems.snapdragon
artifactId: snapdragon-parent
version:    2.7.0
packaging:  pom
```

Itself a child of `org.springframework.boot:spring-boot-starter-parent:4.0.7`.

This is the **2.7.0 / Boot-4 line**. The legacy **1.0.0 / Spring Boot 3.5.5 line**
stays untouched for any BFF that has not yet migrated, but all new and migrated
services target 2.7.0.

## What it provides

- **Properties:** `java.version=25`, UTF-8 encoding, and pinned versions for
  `snapdragon-commons` (2.7.0), the Spring Cloud release train (2025.1.2), SpringDoc
  (3.0.3, the Boot-4 / Spring Framework 7 line), Resilience4j (2.4.0, the Boot-4
  starter line), and the AWS SDK BOM (2.28.3).
- **Common dependencies** (inherited by every reactive BFF): WebFlux, Actuator,
  Security, OAuth2 Resource Server, Validation, Data-R2DBC + r2dbc-postgresql,
  Liquibase (+ `spring-boot-liquibase` runtime module — Boot 4 split
  `LiquibaseAutoConfiguration` out of the core autoconfigure umbrella, so without it
  migrations silently never run), spring-jdbc + postgresql (runtime), SpringDoc
  WebFlux UI; plus the test stack (spring-boot-starter-test, reactor-test,
  spring-security-test, r2dbc-h2, h2, the Boot-4 split test-slice modules
  `spring-boot-webflux-test` / `spring-boot-data-r2dbc-test`, and the Testcontainers
  integration-test infra `spring-boot-testcontainers` + testcontainers-postgresql/testcontainers-junit-jupiter/testcontainers-r2dbc).
- **dependencyManagement:** the Spring Cloud `spring-cloud-dependencies` BOM (import),
  `snapdragon-commons`, AWS SDK BOM (import), Resilience4j
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
  violations** (`:check` goals, `failOnViolation=true`). See the section below.
- **`aspectjweaver`** is included in the dependency set so that `@CircuitBreaker` and
  other Spring AOP annotations from Resilience4j wire automatically across all child
  repos without any per-repo AspectJ configuration.
- **distributionManagement:** the GitLab project Maven Package Registry.

## Static-analysis enforcement (inherited, fail-mode)

Every Java repo that parents off this metapom automatically runs three analysers on
`verify` — the child declares nothing. The curated rulesets are NOT in this repo; they
ship in the resource-only **`systems.snapdragon:snapdragon-build-config`** jar and are
referenced on each plugin's own classpath (PMD `/snapdragon/*.xml`, Checkstyle/SpotBugs
`snapdragon/*.xml`). That is the only mechanism by which a separate repo can see a
ruleset that physically lives elsewhere, and it gives curated rules + automatic
inheritance with one new artifact.

| Plugin | Conventions | Rules | Output |
|--------|-------------|-------|--------|
| `maven-pmd-plugin` | **A**, **B** | `FinalFieldCouldBeStatic`, `ImmutableField` | `target/pmd.xml` |
| `maven-checkstyle-plugin` | **F**, **G**, **H** | `VisibilityModifier`, `FinalClass`, `HideUtilityClassConstructor`, `MutableException`, `LambdaBodyLength` | `target/checkstyle-result.xml` |
| `spotbugs-maven-plugin` + FindSecBugs | **D**, **E** | `EI_EXPOSE_REP*`, `MS_EXPOSE_REP`, `MS_MUTABLE_*`, `MS_SHOULD_BE_FINAL` (include-filtered) | `target/spotbugsXml.xml` |

Convention **C** (enum for fixed string sets) and the *defensive-copy fix* /
*lambda→method-ref* / *nesting* halves of D and H have no reliable low-noise static
rule, so they remain agent-pass conventions — by design, no rule is added that would
flag every lambda or every collection field.

**Fail-mode.** All three analysers run with the `:check` goal and `failOnViolation=true`
(PMD: `pmd:check`; Checkstyle: `checkstyle:check`, `failOnViolation=true`; SpotBugs:
`spotbugs:check`). A violation fails the build. The SpotBugs include filter narrows to
exactly the D/E patterns and `snapdragon/spotbugs-exclude.xml` is the entity/test
baseline so the signal stays high. All three analysers were flipped to fail-mode in
PRs #4 (PMD), #5 (Checkstyle), and #6 (SpotBugs).

**Escape hatch.** `-Dsnapdragon.analysis.skip=true` skips all three (e.g. a fast
inner-loop build); default is `false`, so CI always runs them. To bump a ruleset, edit
`snapdragon-build-config` and bump `${snapdragon-build-config.version}` here — no runtime
artifact churn.

## Using it in a service repo

```xml
<parent>
  <groupId>systems.snapdragon</groupId>
  <artifactId>snapdragon-parent</artifactId>
  <version>2.7.0</version>
  <relativePath/>
</parent>
```

Then remove from the child pom: `java.version`, the common dependency declarations,
and the common test dependencies. Keep only repo-specific dependencies (kafka, sshj,
cassandra, icu4j, webauthn4j, s3, …), repo-specific properties, and any custom plugin
configuration.

The **gateway** repos (Spring Boot 4.0 / Spring Cloud 2025.1) are now on the same
baseline this metapom targets; the 2.7.0 line was deliberately aligned with the
gateway's proven WebFlux + Casdoor reactive JWT resource-server + GraalVM-native
configuration on Java 25.

## What stays per-repo

Repo-specific dependencies are never pulled into the parent. See each service's pom.

## Publishing

CI publishes the POM to the GitLab Maven Package Registry on the default branch / on a
tag via `./mvnw deploy -s settings.xml`. Authentication uses the GitLab-injected
`CI_JOB_TOKEN` (a job-scoped, read-only, auto-expiring credential) read from
`settings.xml` — **no secret is committed**. See `.gitlab-ci.yml`. There is no GitHub
Actions pipeline; CI is GitLab.

For local development, `./mvnw install` writes the POM to `~/.m2` so sibling repos on
the same machine can resolve it offline.

## Current State

- On `main`, the metapom is fully on the **2.7.0 / Boot-4** baseline: Spring Boot
  4.0.7, Spring Cloud 2025.1.2, Java 25, `snapdragon-commons` 2.7.0. PRs through #10
  are merged (Boot-4 migration, static-analysis, testcontainers baseline,
  TIER-A patch bumps, Java 25, testcontainers 2.x bump); there are no outstanding
  feature branches.
- This metapom carries **no application/auth code** — it only pins versions, shared
  starters, plugins, and publishing config. The org's shared security/tenancy code
  lives in `snapdragon-commons` (`systems.snapdragon.commons.*`, 2.7.0), and the
  shared account/session/MFA/Casdoor-admin infrastructure lives in the new
  `snapdragon-auth-core` (2.7.0, depends on commons; consumed by `user-bff` and
  `admin-bff`). Both are downstream consumers of this baseline, not part of it.
- Ecosystem auth model (for context; enforced in the consumer repos, not here):
  Casdoor is the SSO IdP; `login-ui` does the OIDC authorization-code (PKCE)
  redirect; `user-bff` performs the server-side code→token exchange and holds the
  per-session JWT custody/refresh. The browser only ever holds an **opaque
  `bff_`-prefixed session** — the user never sees their Casdoor JWT. The gateway is a
  pure Casdoor-JWT OAuth2 resource server; a pre-security exchange filter swaps `bff_`
  → the internal custody JWT, and authorization is data-driven by the
  `gateway_route_access` Postgres table. Login/session/account logic is being
  relocated from `admin-bff` to `user-bff` (account/session **data** stays in
  `admin-bff-db`, reached over mTLS + `X-Internal-Token`).
- The Spring Cloud Gateway 5.0 route-config move
  (`spring.cloud.gateway.routes` → `spring.cloud.gateway.server.webflux.routes`) is a
  gateway/generator concern, not a metapom concern; this repo only pins the Spring
  Cloud 2025.1.2 train that introduces it.

## Roadmap

This repo is intentionally thin; its roadmap is to **track the org baseline** as the
platform evolves:

- Keep the 2.7.0 line pinned to the same Spring Boot / Spring Cloud train the
  gateways run, and bump shared versions (`snapdragon-commons`, SpringDoc,
  Resilience4j, Testcontainers, AWS SDK) in lockstep across consumers.
- Add `snapdragon-auth-core` to `dependencyManagement` (managed version) once enough
  consumers depend on it, so `user-bff` / `admin-bff` declare it without a `<version>`.
- Retire the H2 pins if/when an upstream Boot-4 r2dbc-h2 release fixes the
  parameter-binding regression.
- Continue publishing only via GitLab CI (`CI_JOB_TOKEN`); no GitHub Actions.
- Downstream platform work this baseline supports (built in the service/UI repos):
  SSO end-to-end + e2e, MFA (WebAuthn + TOTP + recovery, step-up), encrypted
  versioned backups, egress VPN drop-in, per-node attached storage, desktop app
  governance, workload console, device-license registry, multi-tenant superadmin,
  games app-store, A/V via coturn/TURN, and OWASP pen-test + nuclei in the CI pipeline.
