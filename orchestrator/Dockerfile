FROM maven:3.9-eclipse-temurin-21 AS build

WORKDIR /build
COPY pom.xml .
# Warm the dependency cache so code changes don't re-download the world
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q clean package -DskipTests

FROM eclipse-temurin:21-jre-alpine

# Run as an unprivileged user; the app only needs to read its own jar.
RUN adduser -D app
WORKDIR /app
COPY --from=build --chown=app:app /build/target/bittle-orchestrator-*.jar app.jar
RUN chown -R app:app /app
USER app

EXPOSE 8080

# busybox wget works unprivileged; 8080 is not a privileged port.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD wget -q --spider http://localhost:8080/actuator/health || exit 1

ENTRYPOINT ["java", "-jar", "app.jar"]
