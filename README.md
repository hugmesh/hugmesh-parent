# snapdragon-parent

The Snapdragon ecosystem **metapom** (`packaging=pom`). It consolidates the shared
Spring Boot 3.5.5 / Java 21 reactive-BFF baseline so every service repo inherits one
audited set of starters, versions, plugins, and publishing config instead of copying
them.

## Coordinates

```
groupId:    systems.snapdragon
artifactId: snapdragon-parent
version:    1.0.0
packaging:  pom
```

Itself a child of `org.springframework.boot:spring-boot-starter-parent:3.5.5`.

## What it provides

- **Properties:** `java.version=21`, UTF-8 encoding, and pinned versions for
  `snapdragon-commons`, SpringDoc (2.7.0), Resilience4j (2.2.0), AWS SDK BOM (2.28.3).
- **Common dependencies** (inherited by every BFF): WebFlux, Actuator, Security,
  OAuth2 Resource Server, Validation, Data-R2DBC + r2dbc-postgresql, Liquibase +
  spring-jdbc + postgresql (runtime), SpringDoc WebFlux UI; plus the test stack
  (spring-boot-starter-test, reactor-test, spring-security-test, r2dbc-h2, h2).
- **dependencyManagement:** `snapdragon-commons`, AWS SDK BOM (import), Resilience4j,
  SpringDoc — children declare these without a `<version>`.
- **pluginManagement:** compiler, surefire (with the Byte Buddy
  `-Dnet.bytebuddy.experimental=true` flag for newer JDKs), spring-boot-maven-plugin,
  native-maven-plugin.
- **distributionManagement:** the GitLab project Maven Package Registry.

## Using it in a service repo

```xml
<parent>
  <groupId>systems.snapdragon</groupId>
  <artifactId>snapdragon-parent</artifactId>
  <version>1.0.0</version>
  <relativePath/>
</parent>
```

Then remove from the child pom: `java.version`, the common dependency declarations,
and the common test dependencies. Keep only repo-specific dependencies (kafka, sshj,
cassandra, icu4j, webauthn4j, s3, …), repo-specific properties, and any custom plugin
configuration.

The **gateway** repos (Spring Boot 4.0.2 + Spring Cloud 2025.1.0) are an intentional
outlier and do **not** inherit from this parent.

## What stays per-repo

Repo-specific dependencies are never pulled into the parent. See each service's pom.

## Publishing

CI publishes the POM to the GitLab Maven Package Registry on the default branch / on a
tag via `./mvnw deploy -s settings.xml`. Authentication uses the GitLab-injected
`CI_JOB_TOKEN` (a job-scoped, read-only, auto-expiring credential) read from
`settings.xml` — **no secret is committed**. See `.gitlab-ci.yml`.

For local development, `./mvnw install` writes the POM to `~/.m2` so sibling repos on
the same machine can resolve it offline.
