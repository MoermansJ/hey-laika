# PYTHON FLASK APP - JAVA INTEGRATION GUIDE

**Objective:** Update your existing Python Flask app to accept `{robot_id}` in URL routes so the Java orchestrator can properly address individual robot services.

**Current Status:** Your Flask app handles ONE robot per instance (correct)
**Needed Change:** Flask app should validate `robot_id` in URLs

---

## THE KEY INSIGHT

Each Python service knows which robot it is from the environment variable:
```
ROBOT_ID=bittle-1  (for port 5001)
ROBOT_ID=bittle-2  (for port 5002)
```

When Java calls:
```
GET http://localhost:5001/api/robots/bittle-1/status
```

The Python service on port 5001 should:
1. Check that the URL says `bittle-1`
2. Verify it matches the environment variable `ROBOT_ID=bittle-1`
3. If they match → return the data
4. If they don't match → return 404 (wrong service)

This creates a **security layer** and **proper routing**.

---

## UPDATED app/app.py

Replace your existing Flask routes with these robot-aware versions:

```python
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os
import logging

load_dotenv()

app = Flask(__name__)

# Get this service's robot ID from environment
ROBOT_ID = os.getenv('ROBOT_ID', 'default-robot')
MOCK_MODE = os.getenv('MOCK_MODE', 'True') == 'True'

logger = logging.getLogger(__name__)

# ==========================================
# HELPER FUNCTION
# ==========================================

def verify_robot_id(robot_id):
    """
    Verify the robot_id in the URL matches this service's ROBOT_ID
    """
    if robot_id != ROBOT_ID:
        return None, (
            jsonify({"error": f"Robot {robot_id} not found on this service. This service handles {ROBOT_ID}"}),
            404
        )
    return True, None

# ==========================================
# HEALTH & STATUS ENDPOINTS
# ==========================================

@app.route('/api/health', methods=['GET'])
def health():
    """System health check (no robot_id needed)"""
    return jsonify({
        "status": "healthy",
        "robot_id": ROBOT_ID,
        "mode": "mock" if MOCK_MODE else "real",
        "service": "bittle-python"
    })

@app.route('/api/robots/<robot_id>/status', methods=['GET'])
def get_status(robot_id):
    """
    GET /api/robots/{robot_id}/status
    Returns status of the robot
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    # Your existing code to get status
    try:
        status = {
            "robotId": robot_id,
            "connected": True,
            "battery": bittle_controller.battery_level,
            "mode": bittle_controller.communication_method,
            "autonomousRunning": bittle_controller.is_autonomous(),
            "lastUpdate": str(datetime.now())
        }
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error getting status: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# PERSONALITY ENDPOINTS
# ==========================================

@app.route('/api/robots/<robot_id>/personality', methods=['GET'])
def get_personality(robot_id):
    """
    GET /api/robots/{robot_id}/personality
    Returns personality state
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        personality_state = {
            "robotId": robot_id,
            "energy": personality_engine.personality.energy,
            "boredom": personality_engine.personality.boredom,
            "happiness": personality_engine.personality.happiness,
            "curiosity": personality_engine.personality.curiosity,
            "mood": personality_engine.personality.mood,
            "totalInteractions": personality_engine.personality.total_interactions
        }
        return jsonify(personality_state)
    except Exception as e:
        logger.error(f"Error getting personality: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# BEHAVIOR ENDPOINTS
# ==========================================

@app.route('/api/robots/<robot_id>/behavior', methods=['GET'])
def get_next_behavior(robot_id):
    """
    GET /api/robots/{robot_id}/behavior
    Asks Claude what the robot should do next
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        context = request.args.get('context', '')
        behavior = personality_engine.get_next_behavior(context)
        
        return jsonify({
            "robotId": robot_id,
            "action": behavior.get('action'),
            "emotion": behavior.get('emotion'),
            "display": behavior.get('display'),
            "reasoning": behavior.get('reasoning')
        })
    except Exception as e:
        logger.error(f"Error getting behavior: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# COMMAND ENDPOINTS
# ==========================================

@app.route('/api/robots/<robot_id>/command', methods=['POST'])
def execute_command(robot_id):
    """
    POST /api/robots/{robot_id}/command
    Send a command to the robot
    
    Body: {"command": "walk_forward"}
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        data = request.get_json()
        command = data.get('command')
        
        if not command:
            return jsonify({"error": "command required"}), 400
        
        success = bittle_controller.send_command(command)
        
        return jsonify({
            "robotId": robot_id,
            "command": command,
            "success": success
        })
    except Exception as e:
        logger.error(f"Error executing command: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# AUTONOMOUS MODE ENDPOINTS
# ==========================================

@app.route('/api/robots/<robot_id>/autonomous/start', methods=['POST'])
def start_autonomous(robot_id):
    """
    POST /api/robots/{robot_id}/autonomous/start
    Start autonomous behavior loop
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        # Your existing autonomous logic
        bittle_controller.start_autonomous()
        
        return jsonify({
            "robotId": robot_id,
            "status": "started",
            "autonomous": True
        })
    except Exception as e:
        logger.error(f"Error starting autonomous: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/robots/<robot_id>/autonomous/stop', methods=['POST'])
def stop_autonomous(robot_id):
    """
    POST /api/robots/{robot_id}/autonomous/stop
    Stop autonomous behavior loop
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        # Your existing stop logic
        bittle_controller.stop_autonomous()
        
        return jsonify({
            "robotId": robot_id,
            "status": "stopped",
            "autonomous": False
        })
    except Exception as e:
        logger.error(f"Error stopping autonomous: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/robots/<robot_id>/autonomous/status', methods=['GET'])
def autonomous_status(robot_id):
    """
    GET /api/robots/{robot_id}/autonomous/status
    Get autonomous mode status
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        return jsonify({
            "robotId": robot_id,
            "autonomous": bittle_controller.is_autonomous(),
            "mode": "autonomous" if bittle_controller.is_autonomous() else "manual"
        })
    except Exception as e:
        logger.error(f"Error getting autonomous status: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# INTERACTION ENDPOINTS
# ==========================================

@app.route('/api/robots/<robot_id>/interact/<interaction_type>', methods=['POST'])
def log_interaction(robot_id, interaction_type):
    """
    POST /api/robots/{robot_id}/interact/{type}
    Log an interaction (pet, play, talk, feed)
    
    Types: "pet", "play", "talk", "feed"
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    if interaction_type not in ['pet', 'play', 'talk', 'feed']:
        return jsonify({"error": "Invalid interaction type"}), 400
    
    try:
        # Your existing interaction logic
        interaction = Interaction(
            robot_id=robot_id,
            type=interaction_type,
            timestamp=datetime.now()
        )
        InteractionRepository.log_interaction(db_session, interaction)
        
        # Update personality
        personality_engine.update_personality(interaction_type)
        
        return jsonify({
            "robotId": robot_id,
            "interaction": interaction_type,
            "success": True
        })
    except Exception as e:
        logger.error(f"Error logging interaction: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# CHOREOGRAPHY ENDPOINTS
# ==========================================

@app.route('/api/robots/<robot_id>/choreography/list', methods=['GET'])
def list_choreography(robot_id):
    """
    GET /api/robots/{robot_id}/choreography/list
    List available animations
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        animations = choreography_lib.get_animation_names()
        return jsonify({
            "robotId": robot_id,
            "animations": animations
        })
    except Exception as e:
        logger.error(f"Error listing choreography: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/robots/<robot_id>/choreography/execute/<animation_name>', methods=['POST'])
def execute_animation(robot_id, animation_name):
    """
    POST /api/robots/{robot_id}/choreography/execute/{animation_name}
    Execute an animation by name
    
    Animation names: walk_forward, spin_right, wave_arm, play_dead, etc.
    """
    valid, error = verify_robot_id(robot_id)
    if error:
        return error
    
    try:
        animation = choreography_lib.get_animation(animation_name)
        
        if not animation:
            return jsonify({"error": f"Animation '{animation_name}' not found"}), 404
        
        success = bittle_controller.execute_animation(animation)
        
        return jsonify({
            "robotId": robot_id,
            "animation": animation_name,
            "success": success
        })
    except Exception as e:
        logger.error(f"Error executing animation: {e}")
        return jsonify({"error": str(e)}), 500

# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# ==========================================
# STARTUP
# ==========================================

if __name__ == '__main__':
    logger.info(f"Starting Bittle service for robot: {ROBOT_ID}")
    logger.info(f"Mock mode: {MOCK_MODE}")
    
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=os.getenv('DEBUG', 'False') == 'True'
    )
```

---

## WHAT CHANGED

### Old Route (Single Robot Per Service)
```python
@app.route('/api/personality')
def get_personality():
    return jsonify(personality.state())
```

### New Route (Java-Compatible)
```python
@app.route('/api/robots/<robot_id>/personality')
def get_personality(robot_id):
    if robot_id != ROBOT_ID:
        return {"error": "Wrong robot"}, 404
    return jsonify(personality.state())
```

**Why?**
- Java orchestrator addresses services by robot_id
- Python service validates the request is for the right robot
- Enables future multi-robot scenarios
- Creates proper URL hierarchy

---

## DOCKER ENVIRONMENT SETUP

Make sure your `docker-compose.yml` passes `ROBOT_ID`:

```yaml
services:
  python-bittle-1:
    build: ../bittle-ai-companion
    ports:
      - "5001:5000"
    environment:
      - ROBOT_ID=bittle-1              # ← Important!
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ENVIRONMENT=development
      - MOCK_MODE=true
    networks:
      - bittle-network

  python-bittle-2:
    build: ../bittle-ai-companion
    ports:
      - "5002:5000"
    environment:
      - ROBOT_ID=bittle-2              # ← Different!
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - ENVIRONMENT=development
      - MOCK_MODE=true
    networks:
      - bittle-network
```

---

## TESTING THE INTEGRATION

### Test 1: Health Check (No Robot ID)
```bash
curl http://localhost:5001/api/health

# Response:
{
  "status": "healthy",
  "robot_id": "bittle-1",
  "mode": "mock",
  "service": "bittle-python"
}
```

### Test 2: Get Status (With Robot ID)
```bash
curl http://localhost:5001/api/robots/bittle-1/status

# Response:
{
  "robotId": "bittle-1",
  "connected": true,
  "battery": 85.5,
  "mode": "mock"
}
```

### Test 3: Wrong Robot ID (Should Fail)
```bash
curl http://localhost:5001/api/robots/bittle-2/status

# Response (404):
{
  "error": "Robot bittle-2 not found on this service. This service handles bittle-1"
}
```

### Test 4: Execute Command
```bash
curl -X POST http://localhost:5001/api/robots/bittle-1/command \
  -H "Content-Type: application/json" \
  -d '{"command": "walk_forward"}'

# Response:
{
  "robotId": "bittle-1",
  "command": "walk_forward",
  "success": true
}
```

### Test 5: From Java Orchestrator
```bash
# Java calls
curl http://localhost:8080/api/robots/bittle-1/status

# Java translates to
curl http://localhost:5001/api/robots/bittle-1/status

# Python responds
{
  "robotId": "bittle-1",
  "connected": true,
  ...
}
```

---

## COMPLETE FLOW

```
1. Client (Browser/Java)
   GET http://localhost:8080/api/robots/bittle-1/status

2. Java Spring Boot (Port 8080)
   FleetController
   └─ RobotAgent("bittle-1", port=5001)
      └─ PythonServiceClient
         └─ GET http://localhost:5001/api/robots/bittle-1/status

3. Python Flask (Port 5001)
   app.route('/api/robots/<robot_id>/status')
   └─ verify_robot_id("bittle-1")
      ├─ Read env var ROBOT_ID = "bittle-1"
      ├─ Match? ✓ Yes
      └─ Return personality, battery, mood

4. Response Chain
   Python ← response
   Java ← response
   Client ← response
   
   Browser shows: {"robotId": "bittle-1", "battery": 85, ...}
```

---

## SUMMARY

**Your existing Python code stays mostly the same:**
- Claude integration → Unchanged
- Hardware communication → Unchanged
- Database operations → Unchanged
- Personality engine → Unchanged

**What changes:**
- Route URLs now include `{robot_id}`
- Each route validates robot_id matches ROBOT_ID environment variable
- This enables Java orchestrator to address specific services

**Result:**
- Python service on port 5001 handles `bittle-1` only
- Python service on port 5002 handles `bittle-2` only
- Java orchestrator can talk to any of them
- Perfect separation of concerns

---

## Implementation Steps

1. **Copy the updated `app/app.py`** from above
2. **Update your `docker-compose.yml`** to include `ROBOT_ID` environment variables
3. **Test endpoints** using the curl commands above
4. **Then run Java orchestrator** which will call these endpoints

**Java will then be able to:**
```java
RobotAgent bittle1 = new RobotAgent("bittle-1", "Bittle 1", "bittle", 5001, pythonClient);
RobotAgent bittle2 = new RobotAgent("bittle-2", "Bittle 2", "bittle", 5002, pythonClient);

fleetManager.registerRobot(bittle1);
fleetManager.registerRobot(bittle2);

// Now Java can command them independently
bittle1.executeCommand("walk");
bittle2.executeCommand("spin");
```

---

**Perfect integration achieved!** 🚀
