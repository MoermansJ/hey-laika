# BITTLE JAVA ORCHESTRATOR - COMPLETE SETUP GUIDE

**Objective:** Build a Spring Boot management platform that orchestrates Python robot services as independent microservices. Python handles hardware/AI logic, Java handles fleet management and business logic.

**Status:** Phase 0.5 - Parallel Development (Python + Java)
**Architecture:** Microservices - Java orchestrator + Multiple Python services
**Timeline:** 1-2 weeks to complete setup
**Skill Level:** Intermediate Java/Spring Boot

---

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────┐
│  Java Spring Boot Orchestrator              │
│  Port: 8080                                 │
│  ├─ Fleet Management (REST API)            │
│  ├─ Robot Agent Registry                   │
│  ├─ Business Logic                         │
│  └─ Database (PostgreSQL for fleet)        │
└─────────────────────┬───────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
    ┌───▼────┐   ┌───▼────┐   ┌───▼────┐
    │Python  │   │Python  │   │Python  │
    │Service │   │Service │   │Service │
    │Bittle1 │   │Bittle2 │   │BittleN │
    │:5001   │   │:5002   │   │:500N   │
    └────────┘   └────────┘   └────────┘
        │             │             │
    ┌───▼────┐   ┌───▼────┐   ┌───▼────┐
    │Bittle  │   │Bittle  │   │Bittle  │
    │Robot 1 │   │Robot 2 │   │Robot N │
    └────────┘   └────────┘   └────────┘
```

**Key Concept:** 
- Python services are **independent microservices**
- Each service handles ONE robot completely
- Each service has its own database, Claude integration, personality state
- Java is a **thin orchestration layer** that:
  - Creates/manages robot instances (objects)
  - Routes requests to correct Python service
  - Coordinates fleet-level operations
  - Provides unified REST API to clients

---

## TECHNOLOGY STACK

### Java Side
- **Framework:** Spring Boot 3.2+
- **Build Tool:** Maven
- **Language:** Java 17+
- **HTTP Client:** RestTemplate (or WebClient)
- **Database:** PostgreSQL (for fleet/orchestration data)
- **Containerization:** Docker

### Python Side (Existing - No Changes)
- Flask service (one instance per robot)
- SQLite database (per robot)
- Claude SDK integration
- Bittle hardware logic

### Network Communication
- **Protocol:** REST API (JSON)
- **Port Layout:**
  - Java: 8080 (main orchestrator)
  - Python 1: 5001 (Bittle1)
  - Python 2: 5002 (Bittle2)
  - Python N: 500N (BittleN)

---

## COMPLETE PROJECT STRUCTURE

```
bittle-orchestrator/
│
├── pom.xml                              # Maven configuration
├── Dockerfile                           # Java container
├── docker-compose.yml                   # Multi-service setup
├── .env.example                         # Configuration template
│
├── src/main/java/com/bittle/
│   │
│   ├── Bittle.java                      # Main application class
│   │
│   ├── config/
│   │   ├── RestTemplateConfig.java      # HTTP client configuration
│   │   ├── DatabaseConfig.java          # Database configuration
│   │   └── ApplicationProperties.java   # Application properties
│   │
│   ├── model/
│   │   ├── Robot.java                   # JPA entity for database
│   │   ├── RobotService.java            # Robot business entity (not Spring service)
│   │   ├── RobotStatus.java             # DTO for robot status
│   │   ├── RobotBehavior.java           # DTO for behavior
│   │   ├── RobotPersonality.java        # DTO for personality
│   │   └── RobotCommand.java            # DTO for commands
│   │
│   ├── agent/
│   │   ├── RobotAgent.java              # Individual robot agent (main class)
│   │   ├── RobotAgentRegistry.java      # Registry of all agents
│   │   └── RobotAgentFactory.java       # Factory to create agents
│   │
│   ├── fleet/
│   │   ├── FleetManager.java            # Manages multiple robots
│   │   ├── FleetOrchestrator.java       # High-level orchestration logic
│   │   └── FleetCoordinator.java        # Coordinates robot actions
│   │
│   ├── controller/
│   │   ├── FleetController.java         # REST endpoints for fleet operations
│   │   ├── RobotController.java         # REST endpoints for individual robots
│   │   ├── HealthController.java        # Health check endpoints
│   │   └── WebController.java           # Web dashboard endpoints
│   │
│   ├── service/
│   │   ├── RobotServiceImpl.java         # Spring service for robot operations
│   │   ├── FleetServiceImpl.java         # Spring service for fleet operations
│   │   ├── PythonServiceClient.java     # HTTP client to Python services
│   │   └── OrchestrationService.java    # Business logic service
│   │
│   ├── repository/
│   │   ├── RobotRepository.java         # Database operations for robots
│   │   ├── FleetRepository.java         # Database operations for fleet
│   │   └── InteractionRepository.java   # Database operations for interactions
│   │
│   ├── exception/
│   │   ├── RobotNotFoundException.java
│   │   ├── ServiceUnavailableException.java
│   │   └── GlobalExceptionHandler.java
│   │
│   └── util/
│       ├── RobotIdGenerator.java
│       └── PortAllocator.java
│
├── src/main/resources/
│   ├── application.properties            # Spring configuration
│   ├── application-dev.properties        # Development config
│   ├── application-prod.properties       # Production config
│   └── templates/
│       ├── index.html                   # Dashboard
│       └── fleet-status.html            # Fleet overview
│
├── src/test/java/com/bittle/
│   ├── agent/
│   │   └── RobotAgentTest.java
│   ├── fleet/
│   │   └── FleetManagerTest.java
│   ├── service/
│   │   └── PythonServiceClientTest.java
│   └── integration/
│       └── FleetIntegrationTest.java
│
└── README.md                             # Project documentation
```

---

## STEP 1: CREATE SPRING BOOT PROJECT

### Using Maven Archetype
```bash
cd ~
mvn archetype:generate \
  -DgroupId=com.bittle \
  -DartifactId=bittle-orchestrator \
  -DarchetypeArtifactId=maven-archetype-quickstart \
  -DarchetypeVersion=1.4 \
  -DinteractiveMode=false

cd bittle-orchestrator
```

### Or Download Spring Boot Starter
Visit: https://start.spring.io/

Fill in:
- **Project:** Maven
- **Language:** Java
- **Spring Boot:** 3.2.x
- **Group:** com.bittle
- **Artifact:** bittle-orchestrator
- **Java:** 17
- **Dependencies:**
  - Spring Web
  - Spring Data JPA
  - PostgreSQL Driver
  - Spring Boot DevTools
  - Lombok

Click "Generate" → Download → Extract

---

## STEP 2: SETUP pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <groupId>com.bittle</groupId>
    <artifactId>bittle-orchestrator</artifactId>
    <version>0.1.0</version>
    <name>Bittle Orchestrator</name>
    <description>Java management platform for Bittle robot fleet</description>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.source>17</maven.compiler.source>
        <maven.compiler.target>17</maven.compiler.target>
    </properties>

    <dependencies>
        <!-- Spring Boot -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>

        <!-- Database -->
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>

        <!-- Lombok (reduces boilerplate) -->
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <optional>true</optional>
        </dependency>

        <!-- JSON -->
        <dependency>
            <groupId>com.google.code.gson</groupId>
            <artifactId>gson</artifactId>
        </dependency>

        <!-- HTTP Client -->
        <dependency>
            <groupId>org.apache.httpcomponents.client5</groupId>
            <artifactId>httpclient5</artifactId>
        </dependency>

        <!-- Testing -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>

        <!-- Logging -->
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-logging</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
        </plugins>
    </build>

</project>
```

---

## STEP 3: CORE MODEL CLASSES

### `src/main/java/com/bittle/model/RobotStatus.java`
```java
package com.bittle.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class RobotStatus {
    private String robotId;
    private String type;
    private String mode;           // "mock", "serial", "wifi"
    private double batteryLevel;
    private String mood;
    private double energy;
    private LocalDateTime lastSeen;
    private boolean connected;
    private String communicationMethod;
}
```

### `src/main/java/com/bittle/model/RobotBehavior.java`
```java
package com.bittle.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class RobotBehavior {
    private String action;         // "walk", "spin", "wave_arm"
    private String emotion;        // "happy", "curious", "tired"
    private String display;        // What to show on screen
    private String reasoning;      // Why Claude picked this
}
```

### `src/main/java/com/bittle/model/RobotPersonality.java`
```java
package com.bittle.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class RobotPersonality {
    private String robotId;
    private double energy;
    private double boredom;
    private double happiness;
    private double curiosity;
    private String mood;
    private long totalInteractions;
}
```

### `src/main/java/com/bittle/model/RobotCommand.java`
```java
package com.bittle.model;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class RobotCommand {
    private String robotId;
    private String command;
    private String type;           // "animation", "behavior", "system"
}
```

### `src/main/java/com/bittle/model/Robot.java`
```java
package com.bittle.model;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import java.time.LocalDateTime;

@Entity
@Table(name = "robots")
@Data
@NoArgsConstructor
@AllArgsConstructor
public class Robot {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    
    @Column(unique = true)
    private String robotId;
    
    private String name;
    private String type;           // "bittle", "roomba", "drone"
    private String pythonServiceUrl;  // e.g., "http://localhost:5001"
    private int port;              // Which port is this service on
    private String communicationMethod;  // "mock", "serial", "wifi"
    
    private boolean active;
    private double batteryLevel;
    private LocalDateTime lastSeen;
    
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;
}
```

---

## STEP 4: ROBOT AGENT CLASS (Core Concept)

### `src/main/java/com/bittle/agent/RobotAgent.java`

**This is the KEY class—represents ONE robot as an object:**

```java
package com.bittle.agent;

import com.bittle.model.*;
import com.bittle.service.PythonServiceClient;
import lombok.extern.slf4j.Slf4j;
import java.util.HashMap;
import java.util.Map;

@Slf4j
public class RobotAgent {
    
    // Identity
    private final String robotId;
    private final String name;
    private final String type;
    private final int port;
    
    // Service connection
    private final PythonServiceClient pythonClient;
    private final String pythonServiceUrl;
    
    // State
    private RobotStatus status;
    private RobotPersonality personality;
    private boolean autonomous;
    
    public RobotAgent(String robotId, String name, String type, int port, 
                      PythonServiceClient pythonClient) {
        this.robotId = robotId;
        this.name = name;
        this.type = type;
        this.port = port;
        this.pythonClient = pythonClient;
        this.pythonServiceUrl = String.format("http://localhost:%d", port);
        this.autonomous = false;
    }
    
    /**
     * Get current status of this robot
     */
    public RobotStatus getStatus() {
        try {
            status = pythonClient.getRobotStatus(pythonServiceUrl, robotId);
            return status;
        } catch (Exception e) {
            log.error("Failed to get status for robot {}: {}", robotId, e.getMessage());
            return createErrorStatus();
        }
    }
    
    /**
     * Get personality state
     */
    public RobotPersonality getPersonality() {
        try {
            personality = pythonClient.getPersonality(pythonServiceUrl, robotId);
            return personality;
        } catch (Exception e) {
            log.error("Failed to get personality for robot {}: {}", robotId, e.getMessage());
            return null;
        }
    }
    
    /**
     * Ask Claude what this robot should do next
     */
    public RobotBehavior getNextBehavior(String context) {
        try {
            return pythonClient.getNextBehavior(pythonServiceUrl, robotId, context);
        } catch (Exception e) {
            log.error("Failed to get behavior for robot {}: {}", robotId, e.getMessage());
            return null;
        }
    }
    
    /**
     * Execute command on this robot
     */
    public boolean executeCommand(String command) {
        try {
            return pythonClient.sendCommand(pythonServiceUrl, robotId, command);
        } catch (Exception e) {
            log.error("Failed to execute command on robot {}: {}", robotId, e.getMessage());
            return false;
        }
    }
    
    /**
     * Start autonomous mode on this robot
     */
    public boolean startAutonomous() {
        try {
            boolean success = pythonClient.startAutonomous(pythonServiceUrl, robotId);
            if (success) {
                this.autonomous = true;
            }
            return success;
        } catch (Exception e) {
            log.error("Failed to start autonomous for robot {}: {}", robotId, e.getMessage());
            return false;
        }
    }
    
    /**
     * Stop autonomous mode on this robot
     */
    public boolean stopAutonomous() {
        try {
            boolean success = pythonClient.stopAutonomous(pythonServiceUrl, robotId);
            if (success) {
                this.autonomous = false;
            }
            return success;
        } catch (Exception e) {
            log.error("Failed to stop autonomous for robot {}: {}", robotId, e.getMessage());
            return false;
        }
    }
    
    /**
     * Log interaction (pet, play, talk, feed)
     */
    public boolean logInteraction(String interactionType) {
        try {
            return pythonClient.logInteraction(pythonServiceUrl, robotId, interactionType);
        } catch (Exception e) {
            log.error("Failed to log interaction for robot {}: {}", robotId, e.getMessage());
            return false;
        }
    }
    
    /**
     * Execute animation by name
     */
    public boolean executeAnimation(String animationName) {
        try {
            return pythonClient.executeAnimation(pythonServiceUrl, robotId, animationName);
        } catch (Exception e) {
            log.error("Failed to execute animation on robot {}: {}", robotId, e.getMessage());
            return false;
        }
    }
    
    // Getters
    public String getRobotId() { return robotId; }
    public String getName() { return name; }
    public String getType() { return type; }
    public int getPort() { return port; }
    public String getPythonServiceUrl() { return pythonServiceUrl; }
    public boolean isAutonomous() { return autonomous; }
    
    private RobotStatus createErrorStatus() {
        RobotStatus error = new RobotStatus();
        error.setRobotId(robotId);
        error.setConnected(false);
        return error;
    }
}
```

---

## STEP 5: FLEET MANAGER

### `src/main/java/com/bittle/fleet/FleetManager.java`

```java
package com.bittle.fleet;

import com.bittle.agent.RobotAgent;
import com.bittle.model.*;
import lombok.extern.slf4j.Slf4j;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

@Slf4j
public class FleetManager {
    
    // Registry of all robot agents
    private final Map<String, RobotAgent> robots = new ConcurrentHashMap<>();
    
    /**
     * Register a new robot agent
     */
    public synchronized void registerRobot(RobotAgent robot) {
        robots.put(robot.getRobotId(), robot);
        log.info("Registered robot: {} ({})", robot.getRobotId(), robot.getName());
    }
    
    /**
     * Get a specific robot agent
     */
    public RobotAgent getRobot(String robotId) {
        return robots.get(robotId);
    }
    
    /**
     * Get all robots
     */
    public Collection<RobotAgent> getAllRobots() {
        return robots.values();
    }
    
    /**
     * Get status of all robots in fleet
     */
    public Map<String, RobotStatus> getFleetStatus() {
        return robots.values().parallelStream()
            .collect(Collectors.toMap(
                RobotAgent::getRobotId,
                RobotAgent::getStatus
            ));
    }
    
    /**
     * Command all robots to do something
     */
    public Map<String, Boolean> commandAllRobots(String command) {
        log.info("Commanding all robots: {}", command);
        return robots.values().parallelStream()
            .collect(Collectors.toMap(
                RobotAgent::getRobotId,
                robot -> robot.executeCommand(command)
            ));
    }
    
    /**
     * Start autonomous mode on all robots
     */
    public Map<String, Boolean> startAllAutonomous() {
        log.info("Starting autonomous mode for all robots");
        return robots.values().parallelStream()
            .collect(Collectors.toMap(
                RobotAgent::getRobotId,
                RobotAgent::startAutonomous
            ));
    }
    
    /**
     * Stop autonomous mode on all robots
     */
    public Map<String, Boolean> stopAllAutonomous() {
        log.info("Stopping autonomous mode for all robots");
        return robots.values().parallelStream()
            .collect(Collectors.toMap(
                RobotAgent::getRobotId,
                RobotAgent::stopAutonomous
            ));
    }
    
    /**
     * Get total fleet statistics
     */
    public FleetStatistics getFleetStatistics() {
        Map<String, RobotStatus> statuses = getFleetStatus();
        
        double avgBattery = statuses.values().stream()
            .mapToDouble(RobotStatus::getBatteryLevel)
            .average()
            .orElse(0);
        
        long connectedCount = statuses.values().stream()
            .filter(RobotStatus::isConnected)
            .count();
        
        return new FleetStatistics(
            robots.size(),
            connectedCount,
            avgBattery,
            System.currentTimeMillis()
        );
    }
    
    /**
     * Remove robot from fleet
     */
    public synchronized void deregisterRobot(String robotId) {
        robots.remove(robotId);
        log.info("Deregistered robot: {}", robotId);
    }
}
```

### `src/main/java/com/bittle/fleet/FleetStatistics.java`
```java
package com.bittle.fleet;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@NoArgsConstructor
@AllArgsConstructor
public class FleetStatistics {
    private int totalRobots;
    private long connectedRobots;
    private double averageBattery;
    private long timestamp;
}
```

---

## STEP 6: HTTP CLIENT TO PYTHON SERVICES

### `src/main/java/com/bittle/service/PythonServiceClient.java`

```java
package com.bittle.service;

import com.bittle.model.*;
import com.google.gson.Gson;
import com.google.gson.JsonObject;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.HttpClientErrorException;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
public class PythonServiceClient {
    
    private final RestTemplate restTemplate;
    private final Gson gson;
    
    public PythonServiceClient(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
        this.gson = new Gson();
    }
    
    /**
     * Get robot status from Python service
     */
    public RobotStatus getRobotStatus(String serviceUrl, String robotId) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId;
            return restTemplate.getForObject(url, RobotStatus.class);
        } catch (Exception e) {
            log.error("Failed to get status from {}: {}", serviceUrl, e.getMessage());
            throw new ServiceUnavailableException("Python service unavailable: " + serviceUrl);
        }
    }
    
    /**
     * Get personality state from Python service
     */
    public RobotPersonality getPersonality(String serviceUrl, String robotId) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/personality";
            return restTemplate.getForObject(url, RobotPersonality.class);
        } catch (Exception e) {
            log.error("Failed to get personality from {}: {}", serviceUrl, e.getMessage());
            throw new ServiceUnavailableException("Python service unavailable: " + serviceUrl);
        }
    }
    
    /**
     * Get next behavior from Claude (via Python service)
     */
    public RobotBehavior getNextBehavior(String serviceUrl, String robotId, String context) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/behavior";
            if (context != null && !context.isEmpty()) {
                url += "?context=" + context;
            }
            return restTemplate.getForObject(url, RobotBehavior.class);
        } catch (Exception e) {
            log.error("Failed to get behavior from {}: {}", serviceUrl, e.getMessage());
            throw new ServiceUnavailableException("Python service unavailable: " + serviceUrl);
        }
    }
    
    /**
     * Send command to robot (via Python service)
     */
    public boolean sendCommand(String serviceUrl, String robotId, String command) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/command";
            Map<String, String> payload = new HashMap<>();
            payload.put("command", command);
            
            var response = restTemplate.postForObject(url, payload, JsonObject.class);
            return response != null;
        } catch (Exception e) {
            log.error("Failed to send command to {}: {}", serviceUrl, e.getMessage());
            return false;
        }
    }
    
    /**
     * Start autonomous mode
     */
    public boolean startAutonomous(String serviceUrl, String robotId) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/autonomous/start";
            var response = restTemplate.postForObject(url, null, JsonObject.class);
            return response != null;
        } catch (Exception e) {
            log.error("Failed to start autonomous for {}: {}", serviceUrl, e.getMessage());
            return false;
        }
    }
    
    /**
     * Stop autonomous mode
     */
    public boolean stopAutonomous(String serviceUrl, String robotId) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/autonomous/stop";
            var response = restTemplate.postForObject(url, null, JsonObject.class);
            return response != null;
        } catch (Exception e) {
            log.error("Failed to stop autonomous for {}: {}", serviceUrl, e.getMessage());
            return false;
        }
    }
    
    /**
     * Log interaction
     */
    public boolean logInteraction(String serviceUrl, String robotId, String interactionType) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/interact/" + interactionType;
            var response = restTemplate.postForObject(url, null, JsonObject.class);
            return response != null;
        } catch (Exception e) {
            log.error("Failed to log interaction for {}: {}", serviceUrl, e.getMessage());
            return false;
        }
    }
    
    /**
     * Execute animation
     */
    public boolean executeAnimation(String serviceUrl, String robotId, String animationName) {
        try {
            String url = serviceUrl + "/api/robots/" + robotId + "/choreography/execute/" + animationName;
            var response = restTemplate.postForObject(url, null, JsonObject.class);
            return response != null;
        } catch (Exception e) {
            log.error("Failed to execute animation for {}: {}", serviceUrl, e.getMessage());
            return false;
        }
    }
}
```

---

## STEP 7: REST CONTROLLERS

### `src/main/java/com/bittle/controller/FleetController.java`

```java
package com.bittle.controller;

import com.bittle.agent.RobotAgent;
import com.bittle.fleet.FleetManager;
import com.bittle.model.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.*;

@Slf4j
@RestController
@RequestMapping("/api/fleet")
public class FleetController {
    
    @Autowired
    private FleetManager fleetManager;
    
    /**
     * GET /api/fleet/status - Get status of all robots
     */
    @GetMapping("/status")
    public ResponseEntity<Map<String, RobotStatus>> getFleetStatus() {
        Map<String, RobotStatus> status = fleetManager.getFleetStatus();
        return ResponseEntity.ok(status);
    }
    
    /**
     * GET /api/fleet/stats - Get fleet statistics
     */
    @GetMapping("/stats")
    public ResponseEntity<?> getFleetStatistics() {
        return ResponseEntity.ok(fleetManager.getFleetStatistics());
    }
    
    /**
     * GET /api/fleet/robots - List all robots
     */
    @GetMapping("/robots")
    public ResponseEntity<List<Map<String, String>>> listRobots() {
        List<Map<String, String>> robots = new ArrayList<>();
        fleetManager.getAllRobots().forEach(robot -> {
            Map<String, String> info = new HashMap<>();
            info.put("robotId", robot.getRobotId());
            info.put("name", robot.getName());
            info.put("type", robot.getType());
            info.put("port", String.valueOf(robot.getPort()));
            robots.add(info);
        });
        return ResponseEntity.ok(robots);
    }
    
    /**
     * POST /api/fleet/command - Send command to all robots
     */
    @PostMapping("/command")
    public ResponseEntity<Map<String, Boolean>> commandAll(@RequestBody RobotCommand command) {
        Map<String, Boolean> results = fleetManager.commandAllRobots(command.getCommand());
        return ResponseEntity.ok(results);
    }
    
    /**
     * POST /api/fleet/autonomous/start - Start autonomous on all
     */
    @PostMapping("/autonomous/start")
    public ResponseEntity<Map<String, Boolean>> startAllAutonomous() {
        Map<String, Boolean> results = fleetManager.startAllAutonomous();
        return ResponseEntity.ok(results);
    }
    
    /**
     * POST /api/fleet/autonomous/stop - Stop autonomous on all
     */
    @PostMapping("/autonomous/stop")
    public ResponseEntity<Map<String, Boolean>> stopAllAutonomous() {
        Map<String, Boolean> results = fleetManager.stopAllAutonomous();
        return ResponseEntity.ok(results);
    }
}
```

### `src/main/java/com/bittle/controller/RobotController.java`

```java
package com.bittle.controller;

import com.bittle.agent.RobotAgent;
import com.bittle.fleet.FleetManager;
import com.bittle.model.*;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@Slf4j
@RestController
@RequestMapping("/api/robots")
public class RobotController {
    
    @Autowired
    private FleetManager fleetManager;
    
    /**
     * GET /api/robots/{robotId}/status
     */
    @GetMapping("/{robotId}/status")
    public ResponseEntity<RobotStatus> getStatus(@PathVariable String robotId) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(robot.getStatus());
    }
    
    /**
     * GET /api/robots/{robotId}/personality
     */
    @GetMapping("/{robotId}/personality")
    public ResponseEntity<RobotPersonality> getPersonality(@PathVariable String robotId) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(robot.getPersonality());
    }
    
    /**
     * GET /api/robots/{robotId}/behavior
     */
    @GetMapping("/{robotId}/behavior")
    public ResponseEntity<RobotBehavior> getNextBehavior(
            @PathVariable String robotId,
            @RequestParam(required = false, defaultValue = "") String context) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(robot.getNextBehavior(context));
    }
    
    /**
     * POST /api/robots/{robotId}/command
     */
    @PostMapping("/{robotId}/command")
    public ResponseEntity<Map<String, Object>> executeCommand(
            @PathVariable String robotId,
            @RequestBody RobotCommand command) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        boolean success = robot.executeCommand(command.getCommand());
        return ResponseEntity.ok(Map.of("success", success, "robotId", robotId));
    }
    
    /**
     * POST /api/robots/{robotId}/autonomous/start
     */
    @PostMapping("/{robotId}/autonomous/start")
    public ResponseEntity<Map<String, Object>> startAutonomous(@PathVariable String robotId) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        boolean success = robot.startAutonomous();
        return ResponseEntity.ok(Map.of("success", success, "robotId", robotId));
    }
    
    /**
     * POST /api/robots/{robotId}/autonomous/stop
     */
    @PostMapping("/{robotId}/autonomous/stop")
    public ResponseEntity<Map<String, Object>> stopAutonomous(@PathVariable String robotId) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        boolean success = robot.stopAutonomous();
        return ResponseEntity.ok(Map.of("success", success, "robotId", robotId));
    }
    
    /**
     * POST /api/robots/{robotId}/interact/{type}
     */
    @PostMapping("/{robotId}/interact/{type}")
    public ResponseEntity<Map<String, Object>> logInteraction(
            @PathVariable String robotId,
            @PathVariable String type) {
        RobotAgent robot = fleetManager.getRobot(robotId);
        if (robot == null) {
            return ResponseEntity.notFound().build();
        }
        boolean success = robot.logInteraction(type);
        return ResponseEntity.ok(Map.of("success", success, "robotId", robotId, "type", type));
    }
}
```

### `src/main/java/com/bittle/controller/HealthController.java`

```java
package com.bittle.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import com.bittle.fleet.FleetManager;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/health")
public class HealthController {
    
    @Autowired
    private FleetManager fleetManager;
    
    /**
     * GET /api/health - System health check
     */
    @GetMapping
    public ResponseEntity<Map<String, Object>> health() {
        Map<String, Object> health = new HashMap<>();
        health.put("status", "healthy");
        health.put("timestamp", LocalDateTime.now());
        health.put("fleetSize", fleetManager.getAllRobots().size());
        health.put("orchestrator", "Java Spring Boot");
        return ResponseEntity.ok(health);
    }
}
```

---

## STEP 8: APPLICATION MAIN CLASS

### `src/main/java/com/bittle/BittleApplication.java`

```java
package com.bittle;

import com.bittle.agent.RobotAgent;
import com.bittle.fleet.FleetManager;
import com.bittle.service.PythonServiceClient;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.web.client.RestTemplate;

@Slf4j
@SpringBootApplication
public class BittleApplication {
    
    public static void main(String[] args) {
        ApplicationContext context = SpringApplication.run(BittleApplication.class, args);
        
        // Initialize fleet manager and register robots
        FleetManager fleetManager = context.getBean(FleetManager.class);
        PythonServiceClient pythonClient = context.getBean(PythonServiceClient.class);
        
        // Register Bittle 1 (running on port 5001)
        RobotAgent bittle1 = new RobotAgent(
            "bittle-1",
            "Bittle 1",
            "bittle",
            5001,
            pythonClient
        );
        fleetManager.registerRobot(bittle1);
        
        // Register Bittle 2 (running on port 5002) - when available
        // RobotAgent bittle2 = new RobotAgent(
        //     "bittle-2",
        //     "Bittle 2",
        //     "bittle",
        //     5002,
        //     pythonClient
        // );
        // fleetManager.registerRobot(bittle2);
        
        log.info("Bittle Orchestrator started with {} robots", fleetManager.getAllRobots().size());
    }
}
```

---

## STEP 9: CONFIGURATION

### `src/main/resources/application.properties`

```properties
# Spring Boot
spring.application.name=bittle-orchestrator
server.port=8080
server.servlet.context-path=/

# Logging
logging.level.root=INFO
logging.level.com.bittle=DEBUG
logging.file.name=logs/application.log

# Database (for future use - fleet metadata)
spring.datasource.url=jdbc:postgresql://localhost:5432/bittle_fleet
spring.datasource.username=bittle_user
spring.datasource.password=password
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.show-sql=false

# Actuator (for monitoring)
management.endpoints.web.exposure.include=health,metrics
management.endpoint.health.show-details=always

# Application-specific
bittle.python.service.timeout=5000
bittle.fleet.update-interval=10000
```

### `src/main/java/com/bittle/config/RestTemplateConfig.java`

```java
package com.bittle.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;
import org.springframework.boot.web.client.RestTemplateBuilder;
import java.time.Duration;

@Configuration
public class RestTemplateConfig {
    
    @Bean
    public RestTemplate restTemplate(RestTemplateBuilder builder) {
        return builder
            .setConnectTimeout(Duration.ofSeconds(5))
            .setReadTimeout(Duration.ofSeconds(10))
            .build();
    }
}
```

---

## STEP 10: DOCKER SETUP

### `Dockerfile` (Java)

```dockerfile
FROM maven:3.9-eclipse-temurin-17 AS build

WORKDIR /build
COPY pom.xml .
COPY src ./src

RUN mvn clean package -DskipTests

FROM eclipse-temurin:17-jre-slim

WORKDIR /app
COPY --from=build /build/target/bittle-orchestrator-*.jar app.jar

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]
```

### `docker-compose.yml` (Full Stack)

```yaml
version: '3.8'

services:
  
  # Python Service - Bittle 1
  python-bittle-1:
    build:
      context: ../bittle-ai-companion
      dockerfile: Dockerfile
    container_name: bittle-python-1
    ports:
      - "5001:5000"
    environment:
      - ROBOT_ID=bittle-1
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ENVIRONMENT=development
      - MOCK_MODE=true
    volumes:
      - ../bittle-ai-companion/app:/app/app:cached
      - bittle-1-data:/data
    networks:
      - bittle-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  # Python Service - Bittle 2 (Optional)
  # python-bittle-2:
  #   build:
  #     context: ../bittle-ai-companion
  #     dockerfile: Dockerfile
  #   container_name: bittle-python-2
  #   ports:
  #     - "5002:5000"
  #   environment:
  #     - ROBOT_ID=bittle-2
  #     - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
  #     - ENVIRONMENT=development
  #     - MOCK_MODE=true
  #   volumes:
  #     - ../bittle-ai-companion/app:/app/app:cached
  #     - bittle-2-data:/data
  #   networks:
  #     - bittle-network

  # Java Orchestrator
  java-orchestrator:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: bittle-orchestrator
    ports:
      - "8080:8080"
    environment:
      - SPRING_PROFILES_ACTIVE=dev
      - JAVA_OPTS=-Xmx512m -Xms256m
    depends_on:
      python-bittle-1:
        condition: service_healthy
    networks:
      - bittle-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped

networks:
  bittle-network:
    driver: bridge

volumes:
  bittle-1-data:
  # bittle-2-data:
```

---

## STEP 11: EXECUTION

### Build and Run

```bash
# 1. Create new directory for Java project
cd ~
mkdir bittle-orchestrator
cd bittle-orchestrator

# 2. Generate Spring Boot project (use steps from STEP 1)

# 3. Create all the Java files from sections above

# 4. Build
mvn clean package

# 5. Run with Docker Compose
docker-compose up -d

# 6. Check services
docker-compose ps

# 7. View logs
docker-compose logs -f java-orchestrator

# 8. Test endpoints
curl http://localhost:8080/api/health
curl http://localhost:8080/api/fleet/status
curl http://localhost:8080/api/fleet/robots
```

### Test the Integration

```bash
# Get fleet status
curl http://localhost:8080/api/fleet/status

# Get specific robot status
curl http://localhost:8080/api/robots/bittle-1/status

# Get personality
curl http://localhost:8080/api/robots/bittle-1/personality

# Get next behavior
curl http://localhost:8080/api/robots/bittle-1/behavior

# Start autonomous
curl -X POST http://localhost:8080/api/robots/bittle-1/autonomous/start

# Command all robots
curl -X POST http://localhost:8080/api/fleet/command \
  -H "Content-Type: application/json" \
  -d '{"command":"walk"}'
```

---

## STEP 12: PROJECT STRUCTURE IN IDE

After generating files, your IntelliJ project should look like:

```
bittle-orchestrator/
├── .idea/
├── src/
│   ├── main/
│   │   ├── java/com/bittle/
│   │   │   ├── BittleApplication.java
│   │   │   ├── agent/
│   │   │   │   ├── RobotAgent.java
│   │   │   │   └── RobotAgentRegistry.java
│   │   │   ├── config/
│   │   │   │   └── RestTemplateConfig.java
│   │   │   ├── controller/
│   │   │   │   ├── FleetController.java
│   │   │   │   ├── RobotController.java
│   │   │   │   └── HealthController.java
│   │   │   ├── fleet/
│   │   │   │   ├── FleetManager.java
│   │   │   │   └── FleetStatistics.java
│   │   │   ├── model/
│   │   │   │   ├── Robot.java
│   │   │   │   ├── RobotStatus.java
│   │   │   │   ├── RobotBehavior.java
│   │   │   │   ├── RobotPersonality.java
│   │   │   │   └── RobotCommand.java
│   │   │   ├── service/
│   │   │   │   └── PythonServiceClient.java
│   │   │   └── exception/
│   │   │       └── ServiceUnavailableException.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/com/bittle/
│           └── BittleApplicationTests.java
├── target/
├── pom.xml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

---

## ARCHITECTURE SUMMARY

### Data Flow

```
Client Request (Browser/CLI)
  ↓
Java Spring Boot REST Endpoint
  ↓
FleetController or RobotController
  ↓
FleetManager or RobotAgent
  ↓
PythonServiceClient (HTTP call)
  ↓
Python Flask Service (port 5001+)
  ↓
Claude SDK / Database / Hardware
  ↓
Response bubbles back up
```

### Separation of Concerns

```
Java Layer:
├─ Fleet orchestration
├─ Robot instance management
├─ REST API exposure
└─ Business logic

Python Layer (Per Robot):
├─ Hardware communication
├─ Claude integration
├─ Personality state
├─ Database persistence
└─ Behavior execution
```

### Multiple Robots

```
Java Orchestrator registers multiple RobotAgent objects:
  Robot 1 → Python service on port 5001
  Robot 2 → Python service on port 5002
  Robot N → Python service on port 500N

Each completely independent.
Java coordinates them.
```

---

## NEXT STEPS

1. **Generate this project** (follows steps above)
2. **Keep Python services running** (from earlier setup)
3. **Start Java orchestrator** (docker-compose up)
4. **Test endpoints** (curl commands above)
5. **Add dashboard** (optional web UI)
6. **Add persistence** (PostgreSQL for fleet metadata)
7. **Add monitoring** (metrics, health checks)

---

## BENEFITS OF THIS ARCHITECTURE

✅ **Clean separation** - Java doesn't know about hardware
✅ **Scalable** - Add more Python services anytime
✅ **Independent services** - Python services work standalone
✅ **Type safety** - Java's strong typing for management logic
✅ **Easy testing** - Mock Python services or use real ones
✅ **Production ready** - Microservices pattern
✅ **Ready for AWS** - Deploy Java + Python separately
✅ **Future proof** - Can replace/update Python without Java changes

---

## DEBUGGING

```bash
# View Java logs
docker-compose logs -f java-orchestrator

# View Python logs
docker-compose logs -f python-bittle-1

# Check if services are talking
curl -v http://localhost:8080/api/fleet/status

# Debug Java application
# Add breakpoints in IntelliJ, run with debug flag

# Test Python service directly
curl http://localhost:5001/api/health
```

---

**Ready to build!** Pass this to your Claude agent and ask it to generate all the files.
