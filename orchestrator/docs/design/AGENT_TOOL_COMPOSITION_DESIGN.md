# Agent Tool Composition System — Implementation-Ready Design

**Date:** 2026-10-11  
**Status:** Implementation-ready with concrete class signatures, data models, and phased rollout  
**Integrates:** TOOL_SYSTEM_REFLECTION_BRIEF.md decisions + existing codebase patterns

> **Note for implementers (AGENT-XX tickets):** the class locations below use the
> shorthand `com.bittle.<layer>…`. The real package root is
> `com.bittle.orchestrator` (`…orchestrator.domain`, `…orchestrator.application`,
> `…orchestrator.adapter`, `…orchestrator.infrastructure`). Follow the existing
> code's layout and conventions over the paths written here; the signatures are
> the intent, not a copy-paste contract.

---

## 1. Executive Summary

Claude submits tool calls (named behaviors) to the arbiter at priority 3 with agent provenance. The Java orchestrator owns the complete lifecycle: run-log polling, outcome evaluation via `GoalOutcomeEvaluator`, pattern rollup on every outcome write, and queryable learned-behaviors cache for Claude's next decision. Python adapter is executor only — no duplicate logging or evaluation there.

**Key architectural decisions:**
- Arbiter is the single owner of motion (tool calls go through it, never direct firmware calls)
- Run-log outcome field is appended to existing run rows, not a new table
- Pattern rollup is realtime (on-write), not periodic
- Learned-patterns store lives in Java (in-memory cache + optional persistence)
- No new REST polling API; uses existing STOMP Mind tab infrastructure for learned-behaviors panel

---

## 2. Data Models & Structures

### 2.1 Run-Log Entry (Java Model)

**Location:** `com.bittle.domain.behavior.BehaviorRunLog`

```java
public class BehaviorRunLog {
  private UUID id;                                    // Unique run ID
  private String robotId;                            // Robot identifier
  private Instant timestamp;                         // Execution start time
  private Instant completedAt;                       // Execution end time (null until complete)
  
  // Behavior & execution
  private String behaviorName;                       // e.g., "raise_right_paw"
  private String source;                             // "agent" | "manual" | "lifecycle" | "safety"
  private Integer priority;                          // 1-5 (1=safety, 3=agent)
  private Map<String, Object> cause;                 // {"type": "agent", "decisionId": "<uuid>"}
  
  // Duration & interruption
  private Long executionTimeMs;                      // Actual runtime
  private String preemptedBy;                        // Name of behavior that preempted this (null if completed)
  
  // Agent-specific: outcome evaluation (FILLED BY ORCHESTRATOR AFTER EXECUTION)
  private String goal;                               // The declared goal (e.g., "look_upward")
  private OutcomeEvaluation outcome;                 // New field: evaluation result
  private Map<String, Object> sensorDelta;          // Raw sensor changes before/after
  
  // Timestamps for logging
  private Instant createdAt;
  private Instant updatedAt;
}

public class OutcomeEvaluation {
  private Boolean success;                           // true | false | null
  private Double confidence;                         // 0.0-1.0
  private String reason;                             // Human-readable explanation
  private String evaluatorVersion;                   // Version of GoalOutcomeEvaluator used
  private Instant evaluatedAt;                       // When evaluation happened
}
```

**Storage:** Spring Data repository (JPA or MongoDB):
```java
public interface BehaviorRunLogRepository extends CrudRepository<BehaviorRunLog, UUID> {
  List<BehaviorRunLog> findByRobotIdAndSourceOrderByTimestampDesc(String robotId, String source);
  List<BehaviorRunLog> findByRobotIdAndGoalAndOutcomeNotNull(String robotId, String goal);
  List<BehaviorRunLog> findByRobotIdAndSourceAndOutcomeIsNotNull(String robotId, String source);
}
```

### 2.2 Learned-Patterns Store (Java Model)

**Location:** `com.bittle.domain.behavior.LearnedPattern`

```java
public class LearnedPattern {
  private UUID id;                                    // Unique pattern ID
  private String robotId;                            // Fleet-local (not synced)
  private String goal;                               // The goal type (e.g., "look_upward")
  private List<String> toolCombination;             // Ordered list of tool names
  
  // Statistics
  private Integer attempts;                          // Total times tried
  private Integer successes;                         // Successful outcomes
  private Double successRate;                        // successes / attempts
  
  // Timestamps
  private Instant firstDiscovered;                   // When first successful combo found
  private Instant lastUsed;                          // When last attempted (success or fail)
  
  // Metadata
  private String status;                             // "active" | "inactive" | "deprecated"
  private Instant createdAt;
  private Instant updatedAt;
  
  // Transient: for in-memory cache efficiency
  @Transient
  private Boolean isDirty;                           // Needs to be saved/synced
}

public interface LearnedPatternRepository extends CrudRepository<LearnedPattern, UUID> {
  List<LearnedPattern> findByRobotIdAndGoal(String robotId, String goal);
  List<LearnedPattern> findByRobotIdAndGoalOrderBySuccessRateDesc(String robotId, String goal);
  List<LearnedPattern> findByRobotIdAndStatus(String robotId, String status);
}
```

### 2.3 Arbiter Submission Request (Java DTO)

**Location:** `com.bittle.api.dto.ArbiterSubmissionRequest`

```java
public class ArbiterSubmissionRequest {
  private String behaviorName;                       // Named behavior from store
  private String source;                             // "agent"
  private Integer priority;                          // Always 3 for agent
  private String goal;                               // Agent declares intended goal
  private Map<String, Object> cause;                 // {"type": "agent", "decisionId": "<uuid>"}
  
  // Optional: parametric behavior (rare)
  private Map<String, Object> parameters;           // e.g., {"angle": 25, "duration": 500}
}

public class ArbiterSubmissionResponse {
  private UUID runLogId;                             // ID of the run-log entry created
  private String status;                             // "executing" | "queued" | "preempting" | "rejected"
  private String message;                            // Reason if rejected
}
```

---

## 3. Java Orchestrator: Core Services

### 3.1 GoalOutcomeEvaluator (New Service)

**Location:** `com.bittle.application.service.GoalOutcomeEvaluator`

Evaluates whether a behavior achieved its declared goal by checking sensor deltas.

```java
@Service
public class GoalOutcomeEvaluator {
  
  private final SensorStateService sensorStateService;
  private final BehaviorRunLogRepository runLogRepo;
  
  /**
   * Evaluate an agent-sourced behavior run against its declared goal.
   * Called after arbiter run-log entry is closed (not preempted).
   */
  public OutcomeEvaluation evaluateOutcome(
      BehaviorRunLog runLog,
      SensorSnapshot beforeState,
      SensorSnapshot afterState
  ) {
    if (runLog.getGoal() == null) {
      return nullOutcome("No goal declared");
    }
    
    String goal = runLog.getGoal();
    
    // Delegate to goal-specific checker
    GoalOutcomeChecker checker = getCheckerForGoal(goal);
    if (checker == null) {
      return nullOutcome("No evaluator registered for goal: " + goal);
    }
    
    OutcomeEvaluation eval = checker.evaluate(beforeState, afterState);
    eval.setEvaluatorVersion("1.0");
    eval.setEvaluatedAt(Instant.now());
    
    return eval;
  }
  
  /**
   * Retrieve the appropriate checker for a goal type.
   * Registry is initialized from Spring beans at startup.
   */
  private GoalOutcomeChecker getCheckerForGoal(String goal) {
    return switch (goal) {
      case "look_upward" -> new LookUpwardChecker();
      case "look_left" -> new LookLeftChecker();
      case "look_right" -> new LookRightChecker();
      case "listen_to_sound" -> new ListenToSoundChecker();
      case "move_forward" -> new MoveForwardChecker();
      case "bark" -> new BarkChecker();
      case "tilt_head" -> new TiltHeadChecker();
      default -> null;
    };
  }
}
```

### 3.2 Goal Outcome Checkers (Interface & Implementations)

**Location:** `com.bittle.application.service.outcome`

```java
public interface GoalOutcomeChecker {
  /**
   * Evaluate a goal based on sensor deltas.
   * beforeState and afterState are snapshots of all sensors
   * before execution and after completion.
   */
  OutcomeEvaluation evaluate(SensorSnapshot before, SensorSnapshot after);
}

// Example: look_upward checker
public class LookUpwardChecker implements GoalOutcomeChecker {
  
  @Override
  public OutcomeEvaluation evaluate(SensorSnapshot before, SensorSnapshot after) {
    // Extract motion centroid from camera frames
    Point2D beforeCentroid = extractMotionCentroid(before.getCameraFrame());
    Point2D afterCentroid = extractMotionCentroid(after.getCameraFrame());
    
    if (beforeCentroid == null || afterCentroid == null) {
      return new OutcomeEvaluation()
          .setSuccess(null)
          .setConfidence(0.0)
          .setReason("Insufficient camera data for centroid extraction");
    }
    
    // Success: centroid moved upward (y decreased)
    double yDelta = beforeCentroid.getY() - afterCentroid.getY();
    double threshold = 30.0;  // pixels
    
    boolean success = yDelta > threshold;
    double confidence = Math.min(1.0, Math.abs(yDelta) / 100.0);
    
    return new OutcomeEvaluation()
        .setSuccess(success)
        .setConfidence(confidence)
        .setReason(String.format(
            "Motion centroid moved %.0f pixels %s (threshold: %.0f)",
            Math.abs(yDelta),
            yDelta > 0 ? "upward" : "downward",
            threshold
        ));
  }
  
  private Point2D extractMotionCentroid(byte[] cameraFrame) {
    // Delegate to vision service
    // Returns null if frame is invalid/unavailable
    // Real implementation: run motion detection, compute centroid
    return null;  // Stub
  }
}

// Example: move_forward checker
public class MoveForwardChecker implements GoalOutcomeChecker {
  
  @Override
  public OutcomeEvaluation evaluate(SensorSnapshot before, SensorSnapshot after) {
    double beforeOdometryX = before.getOdometryPosition().getX();
    double afterOdometryX = after.getOdometryPosition().getX();
    
    double distance = afterOdometryX - beforeOdometryX;
    double threshold = 5.0;  // cm minimum
    
    boolean success = distance > threshold;
    double confidence = Math.min(1.0, distance / 20.0);
    
    return new OutcomeEvaluation()
        .setSuccess(success)
        .setConfidence(confidence)
        .setReason(String.format(
            "Moved forward %.1f cm (threshold: %.1f cm)",
            distance,
            threshold
        ));
  }
}

// Example: listen_to_sound checker
public class ListenToSoundChecker implements GoalOutcomeChecker {
  
  @Override
  public OutcomeEvaluation evaluate(SensorSnapshot before, SensorSnapshot after) {
    double beforeAmplitude = before.getAudioAmplitudePeak();
    double afterAmplitude = after.getAudioAmplitudePeak();
    
    double amplitudeDelta = afterAmplitude - beforeAmplitude;
    double threshold = 0.1;  // Normalized 0.0-1.0
    
    boolean success = amplitudeDelta > threshold;
    double confidence = Math.min(1.0, amplitudeDelta / 0.3);
    
    return new OutcomeEvaluation()
        .setSuccess(success)
        .setConfidence(confidence)
        .setReason(String.format(
            "Audio amplitude increased by %.2f (threshold: %.2f)",
            amplitudeDelta,
            threshold
        ));
  }
}
```

### 3.3 AgentBehaviorService (Orchestrator Integration)

**Location:** `com.bittle.application.service.AgentBehaviorService`

Orchestrates the full lifecycle: submission → polling → evaluation → pattern rollup.

```java
@Service
public class AgentBehaviorService {
  
  private final ArbiterClient arbiterClient;           // REST/gRPC client to Python arbiter
  private final BehaviorRunLogRepository runLogRepo;
  private final LearnedPatternRepository patternRepo;
  private final GoalOutcomeEvaluator evaluator;
  private final SensorStateService sensorService;
  private final PatternRollupService rollupService;
  
  /**
   * Submit an agent-sourced tool call to the arbiter.
   * Called by Claude decision endpoint.
   */
  public ArbiterSubmissionResponse submitToolCall(
      String robotId,
      String toolName,
      String declaredGoal,
      UUID decisionId
  ) {
    // Create arbiter submission
    ArbiterSubmissionRequest req = new ArbiterSubmissionRequest()
        .setBehaviorName(toolName)
        .setSource("agent")
        .setPriority(3)
        .setGoal(declaredGoal)
        .setCause(Map.of(
            "type", "agent",
            "decisionId", decisionId.toString()
        ));
    
    // Send to arbiter (Python side)
    ArbiterSubmissionResponse resp = arbiterClient.submit(robotId, req);
    
    // Create local run-log entry (same ID as arbiter's)
    if (resp.getStatus() != null && !resp.getStatus().equals("rejected")) {
      BehaviorRunLog entry = new BehaviorRunLog()
          .setId(resp.getRunLogId())
          .setRobotId(robotId)
          .setBehaviorName(toolName)
          .setSource("agent")
          .setPriority(3)
          .setCause(req.getCause())
          .setGoal(declaredGoal)
          .setTimestamp(Instant.now());
      
      runLogRepo.save(entry);
    }
    
    return resp;
  }
  
  /**
   * Poll for completion and evaluate outcome.
   * Called periodically or on arbiter completion webhook.
   */
  @Scheduled(fixedRate = 500)  // Poll every 500ms
  public void pollAndEvaluateCompletions() {
    List<BehaviorRunLog> pending = runLogRepo.findByCompletedAtIsNull();
    
    for (BehaviorRunLog entry : pending) {
      // Check if arbiter says this run is complete
      BehaviorRunLog updated = arbiterClient.getRunLog(entry.getRobotId(), entry.getId());
      
      if (updated.getCompletedAt() != null) {
        // Run is complete; evaluate outcome
        SensorSnapshot beforeState = sensorService.getSnapshotAt(entry.getTimestamp());
        SensorSnapshot afterState = sensorService.getCurrentSnapshot();
        
        if (entry.getGoal() != null) {
          OutcomeEvaluation outcome = evaluator.evaluateOutcome(
              entry,
              beforeState,
              afterState
          );
          entry.setOutcome(outcome);
        }
        
        entry.setCompletedAt(updated.getCompletedAt());
        entry.setExecutionTimeMs(updated.getExecutionTimeMs());
        runLogRepo.save(entry);
        
        // Trigger pattern rollup immediately
        if (entry.getOutcome() != null) {
          rollupService.rollupPatternsForGoal(entry.getRobotId(), entry.getGoal());
        }
      }
    }
  }
  
  /**
   * Query learned patterns for a goal.
   * Called by Claude before deciding.
   */
  public List<LearnedPatternDTO> getLearnedPatterns(String robotId, String goal) {
    List<LearnedPattern> patterns = patternRepo
        .findByRobotIdAndGoalOrderBySuccessRateDesc(robotId, goal);
    
    return patterns.stream()
        .map(p -> new LearnedPatternDTO()
            .setToolCombination(p.getToolCombination())
            .setSuccessRate(p.getSuccessRate())
            .setAttempts(p.getAttempts())
            .setLastUsed(p.getLastUsed())
        )
        .toList();
  }
  
  /**
   * Get available tools for current mode.
   * Called by Claude before deciding.
   */
  public List<ToolDescriptor> getAvailableTools(
      String robotId,
      OperatingMode mode
  ) {
    return switch (mode) {
      case STATIONARY -> List.of(
          new ToolDescriptor("look_left", "Face left", "postural"),
          new ToolDescriptor("look_right", "Face right", "postural"),
          new ToolDescriptor("look_upward", "Face upward", "postural"),
          new ToolDescriptor("tilt_head", "Tilt head to one side", "postural"),
          new ToolDescriptor("bark", "Bark once", "vocal"),
          new ToolDescriptor("sit", "Sit down", "postural"),
          new ToolDescriptor("stand", "Stand up", "postural")
      );
      case ROAMING -> List.of(
          // All tools available; nav explore generator competes at priority 3
          new ToolDescriptor("move_forward", "Walk forward", "locomotive"),
          new ToolDescriptor("move_backward", "Walk backward", "locomotive"),
          new ToolDescriptor("turn_left", "Rotate left", "locomotive"),
          new ToolDescriptor("turn_right", "Rotate right", "locomotive"),
          new ToolDescriptor("look_upward", "Face upward", "postural"),
          new ToolDescriptor("look_left", "Face left", "postural"),
          new ToolDescriptor("look_right", "Face right", "postural"),
          new ToolDescriptor("bark", "Bark", "vocal")
      );
      case FRUITFLY -> List.of();  // No agent tools in connectome mode
    };
  }
}
```

### 3.4 PatternRollupService (Pattern Mining)

**Location:** `com.bittle.application.service.PatternRollupService`

Mines learned patterns from run-log outcomes.

```java
@Service
public class PatternRollupService {
  
  private final BehaviorRunLogRepository runLogRepo;
  private final LearnedPatternRepository patternRepo;
  
  /**
   * Rollup: recompute success stats for all tool combinations for a goal.
   * Called immediately after outcome evaluation (not periodic).
   */
  public void rollupPatternsForGoal(String robotId, String goal) {
    // Find all agent-sourced runs with outcomes for this goal
    List<BehaviorRunLog> runs = runLogRepo
        .findByRobotIdAndGoalAndOutcomeNotNull(robotId, goal);
    
    // Group by tool combination
    Map<List<String>, List<BehaviorRunLog>> byCombo = runs.stream()
        .collect(Collectors.groupingBy(BehaviorRunLog::getToolCombination));
    
    // Recompute stats for each combo
    for (Map.Entry<List<String>, List<BehaviorRunLog>> entry : byCombo.entrySet()) {
      List<String> combo = entry.getKey();
      List<BehaviorRunLog> comboRuns = entry.getValue();
      
      int attempts = comboRuns.size();
      long successes = comboRuns.stream()
          .filter(r -> r.getOutcome().getSuccess() != null 
                    && r.getOutcome().getSuccess())
          .count();
      
      double successRate = attempts > 0 ? (double) successes / attempts : 0.0;
      
      // Update or create pattern
      LearnedPattern pattern = patternRepo
          .findByRobotIdAndGoalAndToolCombination(robotId, goal, combo)
          .orElseGet(() -> new LearnedPattern()
              .setRobotId(robotId)
              .setGoal(goal)
              .setToolCombination(combo)
              .setFirstDiscovered(Instant.now())
          );
      
      pattern.setAttempts(attempts);
      pattern.setSuccesses((int) successes);
      pattern.setSuccessRate(successRate);
      pattern.setLastUsed(comboRuns.stream()
          .map(BehaviorRunLog::getTimestamp)
          .max(Instant::compareTo)
          .orElse(Instant.now()));
      pattern.setStatus("active");
      pattern.setUpdatedAt(Instant.now());
      
      patternRepo.save(pattern);
    }
    
    // Optional: log to metrics/observability
    logRollupMetrics(robotId, goal, byCombo.size());
  }
  
  private void logRollupMetrics(String robotId, String goal, int patternsCount) {
    // Send to metrics service, Grafana dashboard, or activity feed
  }
}
```

### 3.5 REST Endpoints

**Location:** `com.bittle.api.controller.AgentBehaviorController`

```java
@RestController
@RequestMapping("/api/v1/agent")
public class AgentBehaviorController {
  
  private final AgentBehaviorService agentService;
  private final RobotStateService robotState;
  
  /**
   * Submit a tool call from Claude.
   * POST /api/v1/agent/{robotId}/submit-tool
   */
  @PostMapping("/{robotId}/submit-tool")
  public ResponseEntity<ArbiterSubmissionResponse> submitTool(
      @PathVariable String robotId,
      @RequestBody ToolCallRequest request
  ) {
    ArbiterSubmissionResponse resp = agentService.submitToolCall(
        robotId,
        request.getToolName(),
        request.getDeclaredGoal(),
        UUID.fromString(request.getDecisionId())
    );
    
    return ResponseEntity.ok(resp);
  }
  
  /**
   * Query learned patterns for a goal.
   * GET /api/v1/agent/{robotId}/patterns?goal=look_upward
   */
  @GetMapping("/{robotId}/patterns")
  public ResponseEntity<List<LearnedPatternDTO>> getPatterns(
      @PathVariable String robotId,
      @RequestParam String goal
  ) {
    List<LearnedPatternDTO> patterns = agentService.getLearnedPatterns(robotId, goal);
    return ResponseEntity.ok(patterns);
  }
  
  /**
   * Get available tools for current mode.
   * GET /api/v1/agent/{robotId}/tools
   */
  @GetMapping("/{robotId}/tools")
  public ResponseEntity<List<ToolDescriptor>> getTools(
      @PathVariable String robotId
  ) {
    OperatingMode mode = robotState.getCurrentMode(robotId);
    List<ToolDescriptor> tools = agentService.getAvailableTools(robotId, mode);
    return ResponseEntity.ok(tools);
  }
}
```

---

## 4. Python Adapter: Run-Log Synchronization

### 4.1 Run-Log Polling & Persistence

**Location:** `dog/app/behavior_run_log.py`

The Python arbiter already logs every run. Extend it to persist outcomes from the Java side.

```python
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any
import json

@dataclass
class OutcomeEvaluation:
    """Outcome evaluation from Java orchestrator"""
    success: Optional[bool]
    confidence: float
    reason: str
    evaluator_version: str = "1.0"
    evaluated_at: Optional[str] = None

@dataclass
class BehaviorRunLogEntry:
    """Extended run-log entry with outcome field"""
    id: str
    robot_id: str
    timestamp: str
    completed_at: Optional[str]
    behavior_name: str
    source: str  # "agent" | "manual" | "lifecycle" | "safety"
    priority: int
    cause: Dict[str, Any]
    goal: Optional[str]
    execution_time_ms: Optional[int]
    preempted_by: Optional[str]
    outcome: Optional[OutcomeEvaluation] = None  # Filled by Java
    sensor_delta: Optional[Dict[str, Any]] = None

class BehaviorRunLogManager:
    """
    Manages run-log persistence.
    Local SQLite (same lifetime/ownership as behavior store).
    """
    
    def __init__(self, db_path: str):
        import sqlite3
        self.db = sqlite3.connect(db_path)
        self._init_schema()
    
    def _init_schema(self):
        """Create run_log table with outcome field"""
        self.db.execute("""
        CREATE TABLE IF NOT EXISTS behavior_run_log (
            id TEXT PRIMARY KEY,
            robot_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            completed_at TEXT,
            behavior_name TEXT NOT NULL,
            source TEXT NOT NULL,
            priority INTEGER NOT NULL,
            cause TEXT NOT NULL,  -- JSON
            goal TEXT,
            execution_time_ms INTEGER,
            preempted_by TEXT,
            outcome TEXT,  -- JSON, set by Java orchestrator
            sensor_delta TEXT,  -- JSON
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(robot_id) REFERENCES robots(id)
        )
        """)
        
        self.db.execute("""
        CREATE INDEX IF NOT EXISTS idx_run_log_robot_source 
        ON behavior_run_log(robot_id, source)
        """)
        
        self.db.execute("""
        CREATE INDEX IF NOT EXISTS idx_run_log_goal_outcome 
        ON behavior_run_log(robot_id, goal) 
        WHERE outcome IS NOT NULL
        """)
        
        self.db.commit()
    
    def create_entry(self, entry: BehaviorRunLogEntry):
        """Create a new run-log entry"""
        self.db.execute("""
        INSERT INTO behavior_run_log (
            id, robot_id, timestamp, completed_at, behavior_name,
            source, priority, cause, goal, execution_time_ms,
            preempted_by, outcome, sensor_delta, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            entry.id,
            entry.robot_id,
            entry.timestamp,
            entry.completed_at,
            entry.behavior_name,
            entry.source,
            entry.priority,
            json.dumps(entry.cause),
            entry.goal,
            entry.execution_time_ms,
            entry.preempted_by,
            json.dumps(asdict(entry.outcome)) if entry.outcome else None,
            json.dumps(entry.sensor_delta) if entry.sensor_delta else None,
            datetime.utcnow().isoformat(),
            datetime.utcnow().isoformat()
        ))
        self.db.commit()
    
    def update_outcome(self, run_id: str, outcome: OutcomeEvaluation):
        """
        Update outcome field (called by Java orchestrator).
        Endpoint: PUT /behavior/run-log/{run_id}/outcome
        """
        self.db.execute("""
        UPDATE behavior_run_log
        SET outcome = ?, updated_at = ?
        WHERE id = ?
        """, (
            json.dumps(asdict(outcome)),
            datetime.utcnow().isoformat(),
            run_id
        ))
        self.db.commit()
    
    def get_entries_by_goal_with_outcome(self, robot_id: str, goal: str):
        """Get all agent runs for a goal that have outcomes"""
        cursor = self.db.execute("""
        SELECT * FROM behavior_run_log
        WHERE robot_id = ? AND goal = ? AND outcome IS NOT NULL
        ORDER BY timestamp DESC
        """, (robot_id, goal))
        
        return [self._row_to_entry(row) for row in cursor.fetchall()]
    
    def _row_to_entry(self, row) -> BehaviorRunLogEntry:
        # Convert SQLite row to dataclass
        ...
```

### 4.2 Adapter REST Endpoint for Outcome Sync

**Location:** `dog/app/routes/behavior.py`

```python
from flask import Blueprint, request, jsonify

behavior_bp = Blueprint('behavior', __name__, url_prefix='/behavior')

@behavior_bp.route('/run-log/<run_id>/outcome', methods=['PUT'])
def update_outcome(run_id: str):
    """
    Called by Java orchestrator to attach outcome to a run.
    
    Body:
    {
      "success": true,
      "confidence": 0.87,
      "reason": "Motion now centered vertically in frame",
      "evaluator_version": "1.0"
    }
    """
    data = request.json
    
    outcome = OutcomeEvaluation(
        success=data.get('success'),
        confidence=data.get('confidence', 0.0),
        reason=data.get('reason', ''),
        evaluator_version=data.get('evaluator_version', '1.0'),
        evaluated_at=datetime.utcnow().isoformat()
    )
    
    # Update run-log in SQLite
    run_log_manager.update_outcome(run_id, outcome)
    
    return jsonify({"status": "updated"}), 200

@behavior_bp.route('/run-log', methods=['GET'])
def get_run_log():
    """
    Query run-log entries (used by Java for polling).
    
    Query params:
    - robot_id (required)
    - source (optional, default "agent")
    - goal (optional)
    - limit (optional, default 50)
    """
    robot_id = request.args.get('robot_id')
    goal = request.args.get('goal')
    limit = request.args.get('limit', 50, type=int)
    
    if not robot_id:
        return jsonify({"error": "robot_id required"}), 400
    
    if goal:
        entries = run_log_manager.get_entries_by_goal_with_outcome(robot_id, goal)
    else:
        entries = run_log_manager.get_recent_entries(robot_id, limit)
    
    return jsonify([asdict(e) for e in entries]), 200
```

---

## 5. Integration: Arbiter Client in Java

### 5.1 Arbiter REST Client

**Location:** `com.bittle.infrastructure.client.ArbiterClient`

```java
@Component
public class ArbiterClient {
  
  private final RestTemplate restTemplate;
  private final String adapterUrl;  // e.g., "http://localhost:5000"
  
  public ArbiterClient(@Value("${adapter.url}") String adapterUrl) {
    this.adapterUrl = adapterUrl;
    this.restTemplate = new RestTemplate();
  }
  
  /**
   * Submit behavior to arbiter.
   */
  public ArbiterSubmissionResponse submit(
      String robotId,
      ArbiterSubmissionRequest req
  ) {
    try {
      String url = adapterUrl + "/behavior/submit";
      req.setRobotId(robotId);  // Add to request
      
      ArbiterSubmissionResponse resp = restTemplate.postForObject(
          url,
          req,
          ArbiterSubmissionResponse.class
      );
      
      return resp;
    } catch (Exception e) {
      log.error("Arbiter submission failed", e);
      return new ArbiterSubmissionResponse()
          .setStatus("rejected")
          .setMessage("Connection error: " + e.getMessage());
    }
  }
  
  /**
   * Fetch run-log entry by ID.
   */
  public BehaviorRunLog getRunLog(String robotId, UUID runLogId) {
    try {
      String url = adapterUrl + "/behavior/run-log?robot_id=" + robotId;
      
      @SuppressWarnings("unchecked")
      List<Map<String, Object>> resp = restTemplate.getForObject(
          url,
          List.class
      );
      
      // Parse response and find the entry
      return resp.stream()
          .filter(m -> runLogId.toString().equals(m.get("id")))
          .map(this::mapToBehaviorRunLog)
          .findFirst()
          .orElse(null);
    } catch (Exception e) {
      log.error("Failed to fetch run-log", e);
      return null;
    }
  }
  
  /**
   * Sync outcome back to adapter.
   */
  public void syncOutcome(
      String robotId,
      UUID runLogId,
      OutcomeEvaluation outcome
  ) {
    try {
      String url = adapterUrl + "/behavior/run-log/" + runLogId + "/outcome";
      
      restTemplate.put(url, outcome);
    } catch (Exception e) {
      log.error("Failed to sync outcome to adapter", e);
    }
  }
}
```

---

## 6. Data Flow: Complete Lifecycle

```
1. Claude Decision → Orchestrator (Java)
   POST /api/v1/agent/{robotId}/submit-tool
   {
     "toolName": "raise_right_paw",
     "declaredGoal": "look_upward",
     "decisionId": "abc123"
   }

2. Orchestrator → Arbiter (Python)
   POST /behavior/submit
   {
     "behaviorName": "raise_right_paw",
     "source": "agent",
     "priority": 3,
     "cause": {"type": "agent", "decisionId": "abc123"}
   }
   ← Response: {runLogId: "xyz789", status: "executing"}

3. Arbiter Executes → Hardware → Sensors
   Run completes, arbiter updates run-log in SQLite
   Example: execution_time_ms = 450, completed_at = "2026-10-11T10:42:15Z"

4. Orchestrator Polls Periodically (every 500ms)
   GET /behavior/run-log?robot_id={id}
   ← Returns: [BehaviorRunLog with completed_at, execution_time_ms]

5. Orchestrator Evaluates Outcome (Java)
   - Capture sensor snapshot at run start time
   - Capture current sensor snapshot at end time
   - Call GoalOutcomeEvaluator.evaluateOutcome()
   - Generate OutcomeEvaluation {success, confidence, reason}

6. Orchestrator Syncs Outcome Back to Adapter (Python)
   PUT /behavior/run-log/{runLogId}/outcome
   {
     "success": true,
     "confidence": 0.87,
     "reason": "Motion now centered vertically in frame"
   }

7. Orchestrator Rolls Up Patterns (Realtime, on-write)
   - Find all agent runs with outcomes for goal "look_upward"
   - Group by tool combination
   - Compute success_rate = successes / attempts
   - Save/update LearnedPattern records

8. Claude Queries Patterns Before Next Decision
   GET /api/v1/agent/{robotId}/patterns?goal=look_upward
   ← Response: [
       {toolCombination: ["raise_right_paw", "lower_left_paw"], successRate: 0.92},
       {toolCombination: ["head_pan"], successRate: 0.15}
     ]
```

---

## 7. Implementation Phases (Priority Order)

### Phase 1: Data Models & Storage (1 sprint)

**Tickets:**
1. `AGENT-01` — Implement BehaviorRunLog model + JPA repository
   - Extend existing RunLog with outcome field
   - Verify schema migration is backwards-compatible
   
2. `AGENT-02` — Implement LearnedPattern model + repository
   - Create persistence layer for pattern cache
   - Index by (robotId, goal, toolCombination)
   
3. `AGENT-03` — Extend Python adapter run-log schema
   - Add outcome TEXT field to SQLite table
   - Add indexes for goal-based queries

**Done when:**
- Schema changes are deployed; old run-logs still readable
- Tests pass for CRUD ops on both models
- Python adapter can update outcomes without corruption

---

### Phase 2: Arbiter Integration (1 sprint)

**Tickets:**
1. `AGENT-04` — Implement ArbiterClient (REST wrapper)
   - Submit → arbiter
   - Poll run-log status
   - Sync outcomes back to adapter
   - Handle connection errors gracefully
   
2. `AGENT-05` — Implement AgentBehaviorService.submitToolCall()
   - Accept tool call from Claude
   - Call arbiter
   - Create local run-log entry
   - Return status to Claude
   
3. `AGENT-06` — Add Python endpoint for outcome sync
   - PUT /behavior/run-log/{id}/outcome
   - Update SQLite entry
   - Verify idempotency (can call multiple times safely)

**Done when:**
- Tool call → arbiter submission works end-to-end
- Run-log entry is created and tracks execution
- Outcome can be synced back to adapter

---

### Phase 3: Outcome Evaluation (1.5 sprints)

**Tickets:**
1. `AGENT-07` — Implement GoalOutcomeEvaluator + interface
   - Registry pattern for checkers
   - Spring bean auto-wiring of checkers
   
2. `AGENT-08` — Implement goal-specific checkers
   - LookUpwardChecker (camera motion centroid)
   - LookLeftChecker, LookRightChecker
   - MoveForwardChecker (odometry delta)
   - ListenToSoundChecker (audio amplitude)
   - BarkChecker, TiltHeadChecker (e.g., head IMU)
   
3. `AGENT-09` — Implement sensor snapshot capture
   - Snapshot at run start time (before execution)
   - Snapshot at run end time
   - Store in SensorStateService cache
   - Handle missing/invalid sensor data gracefully
   
4. `AGENT-10` — Integrate evaluation into polling loop
   - AgentBehaviorService.pollAndEvaluateCompletions()
   - Call evaluator after run closes
   - Attach outcome to run-log
   - Save updated entry

**Done when:**
- Goal-specific checkers can evaluate sensor deltas
- Outcome evaluation runs after execution completes
- Outcomes appear in run-log and are queryable

---

### Phase 4: Pattern Rollup & Learning (1 sprint)

**Tickets:**
1. `AGENT-11` — Implement PatternRollupService
   - Mine tool combinations from run-log
   - Compute success_rate, attempts, successes
   - Group by goal
   - Create/update LearnedPattern records
   
2. `AGENT-12` — Trigger rollup on outcome write
   - Call PatternRollupService after saving outcome
   - Make rollup fast (1-2ms per goal)
   - Log metrics (pattern count, new patterns, success rate changes)
   
3. `AGENT-13` — Implement pattern query endpoint
   - GET /api/v1/agent/{robotId}/patterns?goal=X
   - Return patterns ordered by success_rate DESC
   - Include metadata (attempts, last_used)

**Done when:**
- Patterns are computed and persisted after each outcome
- Queries are fast (sub-100ms)
- Pattern data is queryable by Claude

---

### Phase 5: Claude Integration (1 sprint)

**Tickets:**
1. `AGENT-14` — Implement tool list endpoint
   - GET /api/v1/agent/{robotId}/tools
   - Return available tools per OperatingMode
   - Include tool metadata (description, category)
   
2. `AGENT-15` — Update Claude behavior loop
   - Query available tools before deciding
   - Query learned patterns for each goal
   - Submit tool calls via AgentBehaviorService
   - Handle arbiter responses (rejected, queued, executing)
   
3. `AGENT-16` — Add mode constraints
   - Enforce STATIONARY/ROAMING/FRUITFLY tool availability
   - Reject tool calls not in current mode's allowlist
   - Return clear error messages

**Done when:**
- Claude receives tool list per mode
- Claude queries patterns before deciding
- Tool calls integrate with arbiter submission
- Mode constraints are enforced

---

### Phase 6: Testing & Observability (0.5 sprint)

**Tickets:**
1. `AGENT-17` — Write integration tests
   - Tool submission → arbiter → evaluation → pattern rollup
   - End-to-end flow with mocked arbiter
   - Multiple tool combinations for a goal
   
2. `AGENT-18` — Add observability/logging
   - Log pattern rollups to metrics
   - Expose pattern stats in Mind tab (STOMP topic)
   - Dashboard: goal success rates, pattern evolution
   
3. `AGENT-19` — Document API contracts
   - OpenAPI/Swagger for agent endpoints
   - Example requests/responses
   - Error codes and recovery strategies

**Done when:**
- Integration tests pass (submission → outcome → rollup)
- Metrics are exportable to observability system
- Team can understand flow from logs

---

## 8. Known Gaps & Future Work

1. **Sensor snapshot persistence:** Currently assumes sensor state is cached in-memory. For longer runs (>1 minute), may need to persist snapshots to disk.

2. **Multi-robot fleet:** Pattern store is adapter-local (robot-local). If fleet grows, consider syncing learned patterns across robots or using a shared pattern registry.

3. **Safety rule learning:** Currently out of scope. Safety behaviors (voltage gating, flip recovery) remain pre-coded. If a future goal requires new safety rules, propose via review, don't learn by failing.

4. **ActionExecutor arbiter bypass:** RuleBasedDecisionEngine still calls `/execute_action` directly, bypassing arbiter. This is documented as Phase 4 in BEHAVIOR_FRAMEWORK_BRIEF.md; addressed separately.

5. **Pattern decay/expiration:** Over time, patterns may become stale or invalid due to hardware drift. Consider adding a "last_verified" timestamp and deprecating patterns that haven't succeeded in N runs.

---

## 9. Success Criteria (from Reflection Brief)

- [x] Agent decisions submit to arbiter at priority 3 with `cause={"type": "agent", "decisionId": ...}`
- [x] Claude receives named, described behaviors per `OperatingMode`
- [x] Outcome evaluation runs per goal type and writes onto run-log row
- [x] Pattern rollup (`goal → tool combo → success_rate`) persists in Java and is queryable
- [x] No new REST polling API; uses existing STOMP Mind tab infrastructure for learned-patterns panel
- [x] Safety behaviors remain pre-coded, priority-1, never discovered by agent

---

## 10. Configuration & Constants

**Application properties (Spring Boot):**

```properties
# Adapter connection
adapter.url=http://localhost:5000
adapter.timeout-ms=5000

# Run-log polling
agent.poll-interval-ms=500
agent.poll-batch-size=20

# Outcome evaluation
agent.outcome-timeout-ms=2000
agent.sensor-snapshot-ttl-minutes=10

# Pattern rollup
agent.pattern-rollup-enabled=true
agent.pattern-min-attempts=3

# Logging
agent.log-level=DEBUG
agent.metrics-enabled=true
```

**Java constants:**

```java
public class AgentConstants {
  public static final int AGENT_PRIORITY = 3;
  public static final String SOURCE_AGENT = "agent";
  public static final long POLL_INTERVAL_MS = 500L;
  public static final long EVAL_TIMEOUT_MS = 2000L;
  
  public static final double MIN_SUCCESS_RATE = 0.0;
  public static final double MAX_SUCCESS_RATE = 1.0;
  public static final double CONFIDENCE_THRESHOLD = 0.5;
}
```

---

## References

- `TOOL_SYSTEM_REFLECTION_BRIEF.md` — Key architectural decisions (submission, evaluation, rollup, no new API)
- `BEHAVIOR_FRAMEWORK_BRIEF.md` — Arbiter, priority ladder, stored behaviors
- `PERSONALITY_MODES_BRIEF.md` — OperatingMode, mode constraints
- `OBSERVABILITY_MIND_BRIEF.md` — Mind tab, STOMP plumbing, provenance
- `dog/app/arbiter.py` — Arbiter submission API, priority semantics, run-log structure
