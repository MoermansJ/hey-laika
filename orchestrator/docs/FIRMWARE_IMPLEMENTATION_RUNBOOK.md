# Firmware Implementation Runbook for CLI Agent

**Status:** Complete design, ready for CLI agent execution  
**Target:** Custom BiBoard firmware with configuration system + audio alerts  
**Phases:** A (Safety), B (Quality), C (Polish) + Configuration + Audio  
**Total Timeline:** 6–8 weeks (full implementation + validation)

---

## **Quick Start for CLI Agent**

### **If You're Starting Now:**

```bash
# 0. Pre-flight check
./scripts/preflight_check.sh

# 1. Backup calibration
curl -s http://localhost:15001/api/servo/command -d '{"command": "c"}' > calibration_backup.json

# 2. Start Phase A implementation
./scripts/phase_a_start.sh

# 3. Follow the checklist below
```

### **Key Documents to Read First**

1. **FIRMWARE_CUSTOM_DESIGN.md** — 10 surgical cuts (the core firmware changes)
2. **FIRMWARE_WEB_CONFIG.md** — Configuration system (what's new in this guide)
3. **FIRMWARE_AUDIO_ALERTS.md** — Audio chirps + voice (battery monitoring)
4. **This document** — Day-by-day implementation guide

---

## **What's New in This Update**

This runbook adds **configuration system + audio alerts** on top of the 10 cuts:

```
Before (Original Design):
  ├─ Cut #1-10 (firmware reliability)
  └─ Done

After (This Update):
  ├─ Cut #1-10 (firmware reliability)
  ├─ + Configuration system (web GUI controls all firmware settings)
  ├─ + Audio alerts (battery chirps + voice announcements)
  ├─ + NVS persistence (settings survive reboot)
  ├─ + Default values (sensible, user-configurable)
  └─ + Testing suite (validate everything)
```

---

## **Implementation Phases (Detailed)**

### **Phase A: Safety + Reliability (2 weeks)**

**Goal:** Fix all firmware race conditions and silent failures.

#### **A.0: Setup (Day 1)**

```bash
# 0.1: Clone and create branch
git clone <fork-url> bittle-custom-fw
cd bittle-custom-fw
git checkout -b phase-a-safety

# 0.2: Install toolchain
sudo apt-get install arduino-cli
arduino-cli core install esp32:esp32@2.0.11
arduino-cli lib install ArduinoWebSockets@2.4.2
arduino-cli lib install ArduinoJson@7.0.4

# 0.3: Verify compilation
arduino-cli compile --fqbn esp32:esp32:esp32 .
# Should return 0 errors

# 0.4: Connect hardware
# USB cable to BiBoard + serial terminal open
picocom /dev/ttyUSB0 -b 115200

# 0.5: Backup everything
c  # Send this command via serial
# Copy output to calibration_backup.txt
```

#### **A.1: Cut #1 - Version Pin (Day 1, 30 min)**

```bash
# File: OpenCat.h:80
# Change: #define DATE "260820" → #define DATE "251121"

# Why: Prevents NVS reset on first flash

# Implementation:
cd firmware/
sed -i 's/#define DATE "260820"/#define DATE "251121"/g' OpenCat.h

# Verify:
grep '#define DATE' OpenCat.h
# Should show: #define DATE "251121"

# Commit:
git add OpenCat.h
git commit -m "Cut #1: Pin version to 251121 (prevent boot reset)"

# ⚠️ DO NOT FLASH YET - wait until all 4 Phase A cuts are done
```

#### **A.2: Cut #2 - WebSocket Queue (Day 2-3, 3 hours)**

```bash
# Files: webServer.h, taskQueue.h, OpenCatEsp32.ino

# What we're fixing:
# - Commands silently dropped when task in flight
# - False ACKs from task queue race
# - Adapter has to guess if command succeeded

# Step 1: Update webServer.h:341-349
# Before:
#   if (!popTask()) { return; }  // Silent drop
#
# After:
#   if (pendingTask.id != 0) {
#     queuedTask = parseCommand(data);
#     sendReply({"status": "queued"});
#     return;
#   }

# Step 2: Restructure taskQueue.h:76-95
# Before: taskQueue[MAX_TASKS] array (but only 1 task active)
#
# After: 
#   struct {
#     Task currentTask;    // Now executing
#     Task queuedTask;     // Waiting if collision
#   }

# Step 3: Fix main loop in OpenCatEsp32.ino:86-95
# Before:
#   loop() {
#     readSignal();
#     popTask();
#     executeTask();
#   }
#
# After:
#   loop() {
#     readSignal();
#     if (isTaskComplete()) popTask();
#     if (queuedTask.id) promoteQueued();
#     executeTask(currentTask);
#   }

# Detailed code changes provided in FIRMWARE_CUSTOM_DESIGN.md, Cut #2 section

git add webServer.h taskQueue.h OpenCatEsp32.ino
git commit -m "Cut #2: Implement WebSocket queue (no silent drops)"

# Testing (post-flash):
# Send: kwkF 1, kwkF 2 back-to-back
# Expected: Both ACKed, both execute in order
```

#### **A.3: Cut #3 - Reflexes Behind Flag (Day 3-4, 2 hours)**

```bash
# File: reaction.h:32-169

# What we're fixing:
# - Auto-flip/knock-recovery triggered unexpectedly
# - Breaks calibration tests
# - Host has no control

# Implementation:
# 1. Add global flag
#   bool allowIMUReflexes = false;  // Default: OFF
#
# 2. Wrap exception handler
#   void dealWithExceptions() {
#     if (isFlipped()) {
#       reportException("flipped");
#       if (allowIMUReflexes) executeSkill(RC);
#     }
#   }
#
# 3. Add token handler
#   case T_IMU_REFLEX_ENABLE:
#     allowIMUReflexes = true;
#   case T_IMU_REFLEX_DISABLE:
#     allowIMUReflexes = false;

# Exception reporting format (Serial + WS):
#   [exception] flipped yaw=245.3 pitch=89.2 roll=12.1
#   [exception] knocked_left force=1.2g

git add reaction.h
git commit -m "Cut #3: Gate IMU reflexes behind flag (report only)"

# Testing (post-flash):
# 1. Default: reflexes off
#    Send: kwkF 10, push dog
#    Expected: No auto-flip, exception "[exception] knocked_left" logged
#
# 2. Enable reflexes
#    Send: T_IMU_REFLEX_ENABLE
#    Push dog again
#    Expected: Auto-flip happens
```

#### **A.4: Cut #4 - De-Latch Gait Counters (Day 4-5, 2 hours)**

```bash
# Files: imu.h:882-936, skill.h, reaction.h

# What we're fixing:
# - kvtL 45 spins forever (yaw-check never runs)
# - Sequential gaits see stale counters
# - Motion jerks or terminates early

# Implementation:
# 1. Move yaw-target check OUT of exception chain
#    void checkMotionCompletion() {
#      if (isTurning() && reachedYawTarget()) {
#        completedCycles++;
#        return true;
#      }
#    }
#
# 2. Call both in loop
#    checkMotionCompletion();  // Motion logic (always runs)
#    checkIMUException();      // Safety (conditional)
#
# 3. Clear counters on start + exception
#    void startGait(...) {
#      cycleCountingMode = false;  // CLEAR FIRST
#      targetCycles = 0;
#      completedCycles = 0;
#      turningQ = false;
#      // NOW set new values
#      cycleCountingMode = true;
#      targetCycles = cycles;
#    }

git add imu.h skill.h reaction.h
git commit -m "Cut #4: De-latch counters (kvtL works, sequential walks clean)"

# Testing (post-flash):
# 1. Clear stale counters
#    kwkF 1, kwkF 2, kwkF 3 (rapid)
#    Expected: No jerk, smooth transitions
#
# 2. Turn-in-place works
#    kvtL 45, gp (check yaw)
#    Expected: Yaw increases to ~45°, stops (doesn't spin)
```

#### **A.5: Compile & Prepare Flash**

```bash
# After all 4 cuts committed:
git log --oneline | head -5
# Should show 4 commits for cuts #1-4

# Full compile
arduino-cli compile --fqbn esp32:esp32:esp32 \
  --board-options "UploadSpeed=921600,CPUFreq=240,FlashMode=qio,FlashFreq=80,FlashSize=4M,PartitionScheme=default_spiffs" \
  .

# If errors: debug and fix before proceeding

# ⚠️ CRITICAL: Calibration backup
echo "Calibration backup: $(date)" >> calibration_backup.txt
c  # Via serial, again

# Ready to flash
```

#### **A.6: Flash Phase A Build**

```bash
# Connected via USB, serial terminal open
python3 -m esptool \
  --chip esp32 \
  --port /dev/ttyUSB0 \
  write_flash \
  0x0 phase-a-build.bin

# Or via Arduino CLI:
arduino-cli upload --fqbn esp32:esp32:esp32 \
  --input <binary> \
  /dev/ttyUSB0

# Monitor output (should NOT see boot prompts):
# "Ready!" (normal boot)
# If "Reset joints' calibration? (Y/n)" appears → VERSION PIN FAILED
```

#### **A.7: Re-Run Calibration Suite**

```bash
# Post-flash: Restore calibration
# Manually type via serial:
c CALIBRATION_VALUES_HERE

# Then run full calibration tests:
python3 /projects/robot/dog/tests/hardware/run_validation_tests.py \
  --test_suite full \
  --output calibration_phase_a.json

# Compare to stock baseline:
# Expected: Error ≤ stock error (should be similar)
# Pass: avg_walk_error < 3%, avg_turn_error < 5°

# If error > stock: Debug the specific cut, review code
```

#### **A.8: Validation Gates (Days 5-7)**

```
✅ GATES TO PASS:
  □ Serial protocol: every command ACKed
  □ WS protocol: no silent drops, no false ACKs
  □ Rapid fire: send 10 commands back-to-back, all execute in order
  □ Reflexes off: no auto-flip during calibration
  □ Counters clean: sequential walks smooth (no jerk)
  □ kvtL works: kwkL/R turns work, kvtL angle-targeted turns work
  □ Calibration error: ≤ stock (< 3%)

If any gate fails:
  1. Review the specific cut
  2. Check code against FIRMWARE_CUSTOM_DESIGN.md
  3. Fix and recompile
  4. Re-flash and re-test
```

---

### **Phase B: Quality + Configuration System (2 weeks)**

**Goal:** Clean yaw math, guarantee motion completion, add configuration system.

#### **B.1: Cut #5 - Wrapped Yaw (Day 8, 1 hour)**

```bash
# File: petoi_icm42670p.cpp:234

# Before:
#   yaw = atan2(...) * RAD_TO_DEG - yawDrift;
#   // No wrapping

# After:
#   yaw = atan2(...) * RAD_TO_DEG - yawDrift;
#   while (yaw >= 180.0f) yaw -= 360.0f;
#   while (yaw < -180.0f) yaw += 360.0f;

# Why: Yaw wraps to [-180, 180), heading math is simple

git add petoi_icm42670p.cpp
git commit -m "Cut #5: Wrap yaw to [-180, 180) (clean heading math)"

# Test:
# Full rotation, gp after each turn
# Expected: yaw stays in range [-180, 180)
```

#### **B.2: Cut #8 - Motion Completion Frames (Day 8-9, 2 hours)**

```bash
# File: skill.h:60, deferSkillTokenEcho mechanism

# Before: No guaranteed motion-end event (adapter guesses with timers)
# After: Every motion queues a terminator that echoes when complete

# Implementation:
# void playSkill(...) {
#   // ...
#   if (skillBlocks || period != 1) {
#     queueDeferredEcho(skillName);
#     if (!hasQueuedTerminator()) {
#       queueTerminator();  // Ensures echo fires
#     }
#   }
# }

git add skill.h
git commit -m "Cut #8: Guarantee motion completion frames (deferred echo)"

# Test:
# Send kwkF 1, kwkF 2, kwkF 3 (one at a time)
# Expected: Each responds with motion_complete frame ~1-2 sec after send
```

#### **B.3: Cut #9 - Clean WS Results (Day 9, 1 hour)**

```bash
# Files: skill.h:60, voice.h:146, exception handler

# Before: Text soup (skill echo + accel dump + voice chatter)
# After: JSON only

# Implementation:
# void printSkillName(...) {
#   Serial.print(skillName);  // Serial only
#   // WS gets JSON motion_complete instead
# }
#
# void sendMotionComplete(String skillName) {
#   StaticJsonDocument<128> doc;
#   doc["type"] = "motion_complete";
#   doc["skill"] = skillName;
#   serializeJson(doc, wsClient);
# }

git add skill.h voice.h
git commit -m "Cut #9: Clean WS results (JSON only, no noise)"

# Test:
# Monitor raw WebSocket output
# Expected: Only JSON frames, no text soup
```

#### **B.4: Configuration System Integration (Days 9-11, 3 hours)**

```bash
# New files:
#   firmware/config.h (structs + defaults)
#   firmware/config_token.h (T_CONFIG_SET handler)
#   firmware/nvsmanager.h (NVS read/write)
#
# Modified files:
#   OpenCat.h (add struct instances)
#   reaction.h (use config flags instead of hardcoded values)

# Key changes:
# 1. Define Config struct (see FIRMWARE_WEB_CONFIG.md)
# 2. Load defaults on boot
# 3. Load persisted values from NVS
# 4. Handle T_CONFIG_SET token
# 5. Save to NVS on change

# Example config struct:
struct MotionConfig {
  bool imu_reflexes_enabled = true;
  uint8_t low_battery_threshold = 5;  // %
  uint8_t low_battery_action = REST;
  float transform_speed = 1.0;
};

struct AudioConfig {
  bool battery_warnings_enabled = true;
  uint8_t battery_thresholds[3] = {25, 15, 5};
  bool voice_battery_pct = true;
  uint8_t chirp_volume = 80;
  uint16_t chirp_frequency = 1000;
};

# Token handler:
case T_CONFIG_SET:
  processConfigToken(token_data);
  saveConfigToNVS();
  print("[config] Setting saved and persisted\n");
  break;

git add firmware/config.h firmware/config_token.h firmware/nvsmanager.h
git commit -m "Add: Configuration system with NVS persistence"

# Test configuration system:
# T_CONFIG_SET motion imu_reflexes_enabled 0
# Expected: "[config] motion.imu_reflexes_enabled = 0"
# Reboot, reflexes should stay disabled
```

#### **B.5: Audio Alerts Integration (Days 11-12, 2 hours)**

```bash
# New files:
#   firmware/audio.cpp (chirp generation)
#   firmware/battery_monitor.cpp (threshold checks)
#
# Modified files:
#   OpenCat.h (include audio.h)
#   config.h (AudioConfig struct)

# Implementation:
# void checkBatteryAndChirp() {
#   uint8_t battery_pct = readBatteryPercentage();
#   
#   if (battery_pct <= 25 && !alerts[0].triggered) {
#     playChirp(1, 200, 100);
#     alerts[0].triggered = true;
#   }
#   // ... check 15%, 5%
# }
#
# void playChirp(uint8_t num_chirps, ...) {
#   for (int i = 0; i < num_chirps; i++) {
#     tone(SPEAKER_PIN, config.audio.chirp_frequency, duration_ms, 
#          config.audio.chirp_volume);
#     delay(duration_ms + gap_ms);
#   }
# }

git add firmware/audio.cpp firmware/battery_monitor.cpp
git commit -m "Add: Audio alerts (battery chirps with configurable thresholds)"

# Test audio:
# 1. Set low_battery_threshold to 95%
# 2. Watch battery level (will trigger immediately)
# 3. Expected: Hear 1 chirp
# 4. Adjust chirp_volume via config
# 5. Expected: Volume changes
```

#### **B.6: Adapter Configuration API (Days 12-13, 3 hours)**

```python
# adapter/config_manager.py
class ConfigManager:
    def get_setting(self, section, key) → value
    def set_setting(self, section, key, value) → {status, old_value, new_value}
    def sync_to_firmware(self, section, key, value)
    def validate(self, section, key, value) → bool

# adapter/app.py
@app.route('/api/config', methods=['GET'])
def get_config(): return full config

@app.route('/api/config/<section>/<key>', methods=['GET'])
def get_setting(section, key): return single setting

@app.route('/api/config/<section>/<key>', methods=['POST'])
def set_setting(section, key): update + sync to firmware

@app.route('/api/config/reset', methods=['POST'])
def reset_config(): reset to defaults

# Test API:
curl http://localhost:15001/api/config
curl http://localhost:15001/api/config/motion
curl -X POST http://localhost:15001/api/config/motion/low_battery_threshold_pct \
  -d '{"value": 8}'
```

#### **B.7: Web GUI Configuration Panel (Days 13-14, 3 hours)**

```tsx
// web/components/ConfigPanel.tsx
// (See FIRMWARE_WEB_CONFIG.md for full component code)

export function ConfigPanel() {
  const [config, setConfig] = useState(null);
  const [synced, setSynced] = useState(true);

  async function updateSetting(section, key, value) {
    // POST to /api/config/{section}/{key}
    // Update local state
    // Show "In Sync" ✓
  }

  return (
    <div>
      <ConfigToggle (imu reflexes)
      <ConfigSlider (low battery)
      <ConfigSlider (transform speed)
      <ConfigToggle (battery warnings)
      <ConfigMultiSelect (warning thresholds)
      <ConfigSlider (chirp volume)
      ... more settings
    </div>
  )
}
```

#### **B.8: Validation Gates (Days 14-15)**

```
✅ GATES TO PASS (Phase B):
  □ Yaw wraps to [-180, 180)
  □ Motion completion echo arrives 1-2 sec after command
  □ No 45s timeouts
  □ WebSocket output is JSON only
  □ Configuration system persists across reboot
  □ Web GUI loads all settings
  □ Web GUI updates reflect in firmware
  □ Battery chirps play at configured thresholds
  □ Chirp volume adjustable via GUI
```

---

### **Phase C: Polish (1-2 weeks, Optional)**

**Goal:** Clean up remaining details, full integration.

#### **C.1: Cut #6, #7, #10 (Days 16-17, 1 hour each)**

```bash
# Cut #6: Disable auto-wander
# Remove z token, randomMind() calls, module activation

# Cut #7: Low-battery alert behind flag
# Report battery, host decides action

# Cut #10: Cosmetics
# Expose transform_speed, safe boot

git add firmware/moduleManager.h firmware/OpenCat.h firmware/reaction.h
git commit -m "Cut #6,#7,#10: Polish (remove auto-wander, battery action, cosmetics)"
```

#### **C.2: Full Integration Testing (Days 17-21)**

```bash
# Long-duration test: 2+ hour exploration run
# - Monitor battery warnings (should chirp at 25%, 15%, 5%)
# - Monitor configuration persistence (change setting, reboot, still set)
# - Monitor motion (no surprises, clean state)
# - Monitor audio (no overlap, clear messages)

# Stress test: 100+ sequential commands
# - No hangs
# - No dropped commands
# - All complete correctly

# Regression test: Compare to Phase B baseline
# - Calibration error unchanged
# - Motion quality unchanged
# - New features don't break old ones
```

#### **C.3: Documentation + Delivery**

```bash
# Compile final build
arduino-cli compile --fqbn esp32:esp32:esp32 .
# Output: build/esp32.esp32.esp32/firmware.bin

# Tag release
git tag -a v1.0-custom-fw -m "Phase A+B+C complete, all tests pass"
git push origin v1.0-custom-fw

# Summarize changes
git log --oneline v0-stock..v1.0-custom-fw > CHANGELOG.md

# Create rollback procedure
echo "To rollback: flash petoi-b10-251121.bin via Arduino CLI"
```

---

## **Testing Checklist**

### **Phase A Validation**

```
Movement:
  ☑ kwkF 1, 2, 3, 5, 6 (no jerk, smooth)
  ☑ kwkL 45, kwkR 45 (smooth turns)
  ☑ kvtL 45 (stops after 45°, doesn't spin)
  ☑ Sequential: kwkF 2 → kwkL 90 → kwkF 2 (L-shape works)

Communication:
  ☑ Send 10 commands rapid-fire, all ACKed
  ☑ All commands execute in order
  ☑ No false ACKs
  ☑ No silent drops

Safety:
  ☑ Default: IMU reflexes OFF
  ☑ Push dog: exception logged, no auto-flip
  ☑ Enable reflexes: now auto-flip happens
  ☑ Calibration error ≤ stock
```

### **Phase B Validation**

```
Heading:
  ☑ Full rotation: yaw stays in [-180, 180)
  ☑ Heading math simplified (no 360° jumps)
  ☑ Delta calculation: new - old (no modulo needed)

Motion Events:
  ☑ Each motion returns completion frame
  ☑ Frame arrives when motion ends (not before)
  ☑ Frame format: {"type": "motion_complete", "skill": "kwkF"}

Configuration:
  ☑ GET /api/config returns all settings
  ☑ POST to setting updates firmware
  ☑ Setting persists after reboot
  ☑ Default values sensible

Audio:
  ☑ Battery 25%: 1 chirp
  ☑ Battery 15%: 2 chirps
  ☑ Battery 5%: 3 chirps
  ☑ Chirp volume control works
  ☑ Chirp frequency adjustable
  ☑ Can disable warnings entirely

Web GUI:
  ☑ Loads configuration
  ☑ Updates reflected in firmware
  ☑ Toggles, sliders, selects all work
  ☑ "In Sync" indicator shows status
```

### **Phase C Validation**

```
Integration:
  ☑ 2-hour exploration run: no hangs, no drops
  ☑ 100+ sequential commands: all complete
  ☑ Battery depletes naturally: chirps at thresholds
  ☑ Reboot mid-exploration: state persisted, continues
  ☑ Configuration survives reboot
```

---

## **Rollback Procedure**

If anything goes wrong at any phase:

```bash
# 1. Stop motion immediately
curl -X POST http://localhost:15001/api/servo/command \
  -d '{"command": "kup"}'

# 2. Download stock firmware
wget https://petoi.io/firmware/b10-251121.bin

# 3. Flash stock
arduino-cli upload --fqbn esp32:esp32:esp32 \
  --input b10-251121.bin /dev/ttyUSB0

# 4. Restore calibration
# Send via serial: c BACKUP_VALUES_HERE

# 5. Back to original state (5 minutes total)

# 6. Analyze what failed
# - Review Phase A/B/C docs
# - Check specific cut implementation
# - Fix + recompile + retry
```

---

## **Day-by-Day Timeline**

```
PHASE A (Safety + Reliability):
  Day 1:  Setup + Cut #1 (version pin)
  Day 2:  Cut #2a (start WebSocket queue)
  Day 3:  Cut #2b (finish WS) + Cut #3 (reflexes)
  Day 4:  Cut #4 (de-latch counters)
  Day 5:  Compile + prepare flash
  Day 6:  Flash + re-run calibration
  Day 7:  Validation + debug (if needed)
  ___________________
  
PHASE B (Quality + Configuration):
  Day 8:  Cut #5 (yaw) + Cut #8 (completion frames)
  Day 9:  Cut #9 (clean WS) + config system start
  Day 10: Config system integration
  Day 11: Audio alerts integration
  Day 12: Adapter API implementation
  Day 13: Web GUI implementation
  Day 14: Validation + debug
  Day 15: Full stress testing
  ___________________
  
PHASE C (Polish):
  Day 16: Cuts #6, #7, #10
  Day 17: Compile + test
  Day 18-21: Integration testing + documentation
```

**Total: 21 working days ≈ 5 weeks (with debugging buffer)**

---

## **CLI Agent Instructions**

Your role is to:

1. **Execute each cut carefully**, following FIRMWARE_CUSTOM_DESIGN.md
2. **Compile and test after every phase**, not just at the end
3. **Log all results** in a markdown file for human review
4. **Abort and escalate if** compilation fails, test gates fail, or unexpected behavior appears
5. **Document workarounds** for any non-standard issues
6. **Provide daily summary** of progress and next steps

### **Example Daily Log**

```markdown
# Firmware Implementation Log

## Day 1: Setup + Cut #1

### Task
- [ ] Preflight check (toolchain, hardware)
- [ ] Backup calibration
- [ ] Apply Cut #1 (version pin)

### Results
✅ Arduino-cli installed
✅ Calibration backed up: 12-byte offset array
✅ Cut #1 applied (OpenCat.h:80 changed)

### Next
→ Day 2: Cut #2 WebSocket queue implementation

---

## Day 2: Cut #2a (WebSocket)

...
```

---

## **Success Criteria (Overall)**

```
✅ Phase A PASS:
  • 0 compilation errors
  • 0 boot prompts on first flash
  • Calibration error ≤ stock
  • No silent drops or false ACKs

✅ Phase B PASS:
  • Motion completion echoes arrive reliably
  • Configuration system persists
  • Audio alerts play correctly
  • Web GUI controls firmware

✅ Phase C PASS:
  • 2-hour integration test with no hangs
  • 100+ commands execute flawlessly
  • Battery alerts fire at correct thresholds
  • Settings survive reboot
```

---

## **Escalation Protocol**

If you encounter any of these, **STOP and escalate to human**:

```
🔴 CRITICAL:
  • Compilation fails (not just warnings)
  • Board won't boot (serial hangs forever)
  • Calibration error > stock + 2%
  • Silent command drops persist after Cut #2

🟡 WARNING:
  • Motion feels jerky (even after Cut #4)
  • Audio chirps have dropout
  • Configuration doesn't persist
  • Web GUI doesn't update firmware
  
Action: Halt current phase, document state, escalate with logs
```

---

## **Reference Documents**

| Document | Content |
|----------|---------|
| FIRMWARE_CUSTOM_DESIGN.md | 10 surgical cuts (core firmware changes) |
| FIRMWARE_WEB_CONFIG.md | Configuration system (web GUI + API) |
| FIRMWARE_AUDIO_ALERTS.md | Battery chirps + voice system |
| FIRMWARE_CUTS_QUICK_REF.md | Quick reference (before/after tables) |
| FIRMWARE_RESET_MAPPING.md | Problem → solution mapping |
| This document | Implementation runbook for CLI agent |

---

**You have all the information needed. Ready to build custom firmware. 🚀**

Proceed to FIRMWARE_CUSTOM_DESIGN.md and start Day 1 of Phase A.

