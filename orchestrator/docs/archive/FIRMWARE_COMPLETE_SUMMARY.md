> **Archived 2026-09-02.** Superseded by [design/FIRMWARE_RESET.md](../design/FIRMWARE_RESET.md); kept for history. Details here no longer match the code.

# Complete Firmware Roadmap: All Components Integrated

**Status:** ✅ All design complete, ready for CLI agent implementation  
**Total Scope:** 10 firmware cuts + Configuration system + Audio alerts system  
**Timeline:** 5–8 weeks (including validation)  
**Deliverable:** Production-ready custom BiBoard firmware

---

## **Document Index (Read in This Order)**

### **1. Core Firmware Design** (Original 10 Cuts)
📄 **FIRMWARE_CUSTOM_DESIGN.md** (80+ KB, comprehensive)  
├─ Philosophy: "Tell me, don't act" (host-controlled, not autonomous)  
├─ 10 surgical cuts organized in 3 phases:  
│  ├─ **Phase A (2 weeks):** Safety + reliability (4 cuts)  
│  │  ├─ Cut #1: Version pin (prevent calibration wipe)  
│  │  ├─ Cut #2: WebSocket queue (no silent drops)  
│  │  ├─ Cut #3: Reflexes behind flag (no ghost motion)  
│  │  └─ Cut #4: De-latch counters (kvtL works, clean state)  
│  │  
│  ├─ **Phase B (1-2 weeks):** Quality (3 cuts)  
│  │  ├─ Cut #5: Wrapped yaw (math works)  
│  │  ├─ Cut #8: Motion completion frames (no guessing)  
│  │  └─ Cut #9: Clean WS results (JSON only)  
│  │  
│  └─ **Phase C (1 week, optional):** Polish (3 cuts)  
│     ├─ Cut #6: Disable auto-wander  
│     ├─ Cut #7: Low-battery alert (host decides)  
│     └─ Cut #10: Cosmetics  
│  
├─ Before/after code for every cut  
├─ Testing gates for each phase  
└─ Rollback procedure (5 minutes to stock)

**Read this first** to understand what we're fixing and why.

---

### **2. Configuration System** (NEW in this update)
📄 **FIRMWARE_WEB_CONFIG.md** (60+ KB)  
├─ All firmware settings configurable via web GUI  
├─ Sensible defaults:  
│  ├─ **Motion:**  
│  │  ├─ IMU auto-recovery: **ON** (flip only, not knock-recovery)  
│  │  ├─ Low battery threshold: **5%** (down from stock's 7%)  
│  │  └─ Low battery action: **rest** (or report-only)  
│  │  
│  ├─ **Audio & Alerts:** (NEW)  
│  │  ├─ Battery warnings: **ENABLED**  
│  │  ├─ Warning thresholds: **25%, 15%, 5%**  
│  │  ├─ Chirp volume: **80%** (0-100 adjustable)  
│  │  ├─ Chirp frequency: **1000 Hz** (adjustable)  
│  │  └─ Voice announcements: **OFF** (Phase C, when TTS ready)  
│  │  
│  └─ **Behavior:**  
│     ├─ Auto-wander: **OFF**  
│     ├─ Personality engine: **ON**  
│     └─ Exploration mode: **frontier-based**  
│  
├─ REST API for updating settings  
│  └─ `/api/config` (GET all)  
│  └─ `/api/config/{section}/{key}` (GET/POST single)  
│  └─ `/api/config/reset` (reset to defaults)  
│  
├─ Web GUI React components  
│  └─ Toggles, sliders, selects, multi-select  
│  
├─ NVS persistence (survives reboot)  
└─ Sync flow: GUI → Adapter API → BiBoard (via T_CONFIG_SET token)

**Read this to understand configuration architecture.**

---

### **3. Audio Alerts & Voice** (NEW in this update)
📄 **FIRMWARE_AUDIO_ALERTS.md** (50+ KB)  
├─ **Phase B (Now):** Chirp alerts  
│  ├─ Battery 25%: 1 chirp (mild reminder)  
│  ├─ Battery 15%: 2 chirps (warning)  
│  ├─ Battery 5%: 3 chirps (critical)  
│  ├─ Chirp frequency: configurable (default 1000 Hz)  
│  ├─ Chirp volume: configurable via GUI (default 80%)  
│  └─ Debounce: only chirp once per level  
│  
├─ **Phase C (Future):** Voice announcements  
│  ├─ Requires: Eleven Labs TTS API ($0/month for most users)  
│  ├─ Example: "Your battery is 23 percent"  
│  ├─ Critical: "Battery 4 percent, entering rest mode"  
│  └─ Integration: Adapter → Eleven Labs → BiBoard (MAX98357A speaker)  
│  
├─ Battery monitoring (every 1 second)  
├─ No impact on motion  
├─ Fallback: if voice fails, chirps still work  
└─ Cost: ~$0.30/month (Eleven Labs, optional)

**Read this to understand battery alert system.**

---

### **4. Implementation Runbook for CLI Agent**
📄 **FIRMWARE_IMPLEMENTATION_RUNBOOK.md** (80+ KB)  
├─ **Day-by-day breakdown** (21 working days, 5 weeks)  
├─ **Phase A (Days 1-7):** Safety + Reliability  
│  └─ 4 cuts implemented + validated  
├─ **Phase B (Days 8-15):** Quality + Configuration + Audio  
│  └─ 3 cuts + config system + audio integration + web GUI  
├─ **Phase C (Days 16-21):** Polish + Integration  
│  └─ 3 optional cuts + full 2-hour testing  
├─ Detailed implementation steps for every cut  
├─ Compilation & flash procedures  
├─ Testing gates (must pass to proceed)  
├─ Rollback instructions  
├─ Escalation protocol (stop & alert if problems)  
└─ Daily logging template

**Read this to execute the implementation.**

---

### **5. Quick Reference**
📄 **FIRMWARE_CUTS_QUICK_REF.md**  
├─ All 10 cuts at a glance  
├─ Before/after table for each  
├─ Implementation checklist  
├─ Success criteria  
└─ Decision matrix (when to flash Phase A)

**Use this as a quick lookup during implementation.**

---

### **6. Problem → Solution Mapping**
📄 **FIRMWARE_RESET_MAPPING.md**  
├─ Every anomaly from calibration tests  
├─ Root cause (line of code)  
├─ What your adapter had to work around  
├─ How the firmware cut fixes it  
├─ Examples: silent drops, false ACKs, kvtL spinning, lay-down animation, etc.

**Use this to understand WHY each cut matters.**

---

## **What Changed (vs. Original Design)**

### **Added: Configuration System**
✨ **Benefit:** All firmware settings controllable via GUI, persist across reboot

```
Before (Original Design):
  "Low battery threshold is hardcoded to 7%"
  → To change: modify firmware, recompile, reflash

After (This Update):
  "Adjust slider in Web GUI: 5%"
  → Instantly synced to firmware
  → Persists across reboot
  → No recompilation needed
```

### **Added: Audio Alerts**
✨ **Benefit:** Battery warnings (chirps + optional voice announcements)

```
Before:
  Battery depletes silently
  → No warning until auto-rest fires
  → User unaware until dog stops

After:
  Battery 25%: 1 chirp
  Battery 15%: 2 chirps  
  Battery 5%: 3 chirps + (Phase C) "Battery 5 percent, entering rest mode"
  → User aware of battery status in real-time
  → Can plan to dock proactively
```

### **Added: Web GUI Configuration Panel**
✨ **Benefit:** No CLI commands needed, visual interface for all settings

```
Motion Settings:
  ☑ IMU Auto-Recovery
  Threshold: [slider] 5% (0-20%)
  Action: [dropdown] rest | report_only
  
Audio & Alerts:
  ☑ Battery Warnings
  Thresholds: [checkboxes] 25% 15% 5%
  Volume: [slider] 80%
  Frequency: 1000 Hz
  
[Reset to Defaults] [Export Config] [Import Config]
[🔄 Sync to Device] ✓ In Sync
```

---

## **Default Configuration (Out of Box)**

```json
{
  "motion": {
    "imu_reflexes_enabled": true,          // Auto-flip ON
    "imu_reflex_type": "flip_only",        // Not knock-recovery
    "low_battery_threshold_pct": 5,        // 5% (was 7%)
    "low_battery_action": "rest",          // Auto-rest when battery low
    "transform_speed": 1.0,                // Normal animation speed
    "max_tilt_degrees": 45                 // Safety limit
  },
  "audio": {
    "battery_warnings_enabled": true,      // Chirps ON
    "battery_warning_thresholds": [25, 15, 5],
    "voice_battery_percentage": true,      // Announce % (when voice ready)
    "chirp_volume": 80,                    // 80% volume
    "chirp_frequency_hz": 1000,            // 1kHz tone
    "voice_enabled": false                 // Voice OFF (Phase C)
  },
  "behavior": {
    "auto_wander_enabled": false,
    "personality_enabled": true,
    "exploration_mode": "frontier"
  }
}
```

**All adjustable via Web GUI, no CLI needed.**

---

## **Architecture Overview**

```
┌────────────────────────────────────────────────────────┐
│                     Web Browser                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Configuration Panel (React Component)          │  │
│  │  ├─ Motion Settings (toggles, sliders)         │  │
│  │  ├─ Audio & Alerts (volume, thresholds)        │  │
│  │  ├─ Behavior (wander, personality mode)        │  │
│  │  └─ [Apply] [Reset] [Import/Export]            │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
                      ↓ HTTP REST
                      
┌────────────────────────────────────────────────────────┐
│              Python Flask Adapter                      │
│  (localhost:15001)                                     │
│  ├─ /api/config → GET all settings                   │
│  ├─ /api/config/{section}/{key} → GET/POST single   │
│  ├─ /api/config/reset → Reset to defaults           │
│  └─ Validates + stores in config/bittle_config.json │
└────────────────────────────────────────────────────────┘
                      ↓ WebSocket
           T_CONFIG_SET motion imu_reflexes_enabled 1
           
┌────────────────────────────────────────────────────────┐
│          BiBoard Firmware (Custom)                     │
│  ├─ Receives T_CONFIG_SET token                      │
│  ├─ Updates in-memory config struct                  │
│  ├─ Saves to NVS (persistent)                        │
│  ├─ Applies new settings immediately                │
│  └─ Battery monitor uses config.audio.thresholds   │
│     → Chirps at 25%, 15%, 5%                        │
└────────────────────────────────────────────────────────┘
                      ↓ Audio
          Speaker plays 1, 2, or 3 chirps
```

---

## **Feature Checklist**

### **Core Firmware Fixes**
- ✅ **Cut #1:** Version pin (prevent calibration wipe on flash)
- ✅ **Cut #2:** WebSocket queue (no silent drops or false ACKs)
- ✅ **Cut #3:** Reflexes behind flag (IMU exceptions reported, not acted)
- ✅ **Cut #4:** De-latch counters (kvtL angle-targeted turns work, clean state)
- ✅ **Cut #5:** Wrapped yaw (heading math clean, [-180, 180))
- ✅ **Cut #8:** Motion completion frames (guaranteed motion-end event)
- ✅ **Cut #9:** Clean WebSocket results (JSON only)
- ✅ **Cut #6:** Disable auto-wander (optional, Phase C)
- ✅ **Cut #7:** Low-battery alert (host decides action, Phase C)
- ✅ **Cut #10:** Cosmetics (Phase C)

### **Configuration System** (NEW)
- ✅ Web GUI configuration panel
- ✅ REST API for settings
- ✅ NVS persistent storage
- ✅ Default sensible values
- ✅ Type validation
- ✅ Import/export configuration
- ✅ Sync flow (GUI → Adapter → Firmware)

### **Audio & Battery Alerts** (NEW)
- ✅ Battery threshold monitoring
- ✅ Chirp generation (1, 2, 3 chirps)
- ✅ Volume control (0-100%)
- ✅ Frequency adjustable
- ✅ Debounce (only chirp once per level)
- ✅ Voice announcements (Phase C, optional)
- ✅ Eleven Labs TTS integration (Phase C)
- ✅ Fallback (voice fails → chirps still work)

### **Integration**
- ✅ Adapter API implementation
- ✅ Web GUI React components
- ✅ Firmware token handler (T_CONFIG_SET)
- ✅ NVS manager (read/write config)
- ✅ Battery monitor task
- ✅ Chirp audio generation

---

## **Testing Strategy**

### **Phase A Validation (Days 5-7)**
```
✅ Serial protocol: every command ACKed
✅ WebSocket: no drops, no false ACKs
✅ Rapid fire: 10 commands back-to-back all execute
✅ Reflexes: off by default, no auto-flip
✅ Counters: sequential walks smooth
✅ kvtL: angle-targeted turn works
✅ Calibration: error ≤ stock
```

### **Phase B Validation (Days 14-15)**
```
✅ Yaw: [-180, 180) wrapping
✅ Completion: motion echo arrives 1-2 sec after command
✅ Configuration: persists across reboot
✅ Web GUI: loads and controls firmware
✅ Battery alerts: chirps at 25%, 15%, 5%
✅ Chirp volume: adjustable via GUI
```

### **Phase C Validation (Days 18-21)**
```
✅ 2-hour integration test (no hangs)
✅ 100+ sequential commands (no drops)
✅ Battery depletion (chirps at right times)
✅ Reboot mid-operation (state persists)
```

---

## **Hardware Required**

```
BiBoard V1.0:
  ✅ MPU6050 IMU (already on board)
  ✅ WiFi (ESP32-MINI-1)
  ✅ GPIO for speaker output (Cut #8 uses tone())
  
Optional (for voice, Phase C):
  ✅ MAX98357A amplifier (already ordered)
  ✅ Piezo speaker or audio jack (already ordered)
  ✅ INMP441 microphone (for future voice input)

No additional hardware required for Phase A or B.
```

---

## **Timeline at a Glance**

```
Week 1: Phase A (Safety + Reliability)
  ✅ 4 cuts implemented
  ✅ Calibration re-validated
  ✅ All tests pass
  
Week 2-3: Phase B (Quality + Configuration + Audio)
  ✅ 3 cuts implemented
  ✅ Configuration system built
  ✅ Audio alerts integrated
  ✅ Web GUI working
  ✅ Full stress testing
  
Week 4: Phase C (Polish) - Optional
  ✅ 3 cosmetic cuts
  ✅ Long-duration integration tests
  ✅ Documentation complete

Total: 4-5 weeks for all (Phase A+B mandatory, C optional)
```

---

## **Success Looks Like**

### **Day 1 Morning**
```
Git clone fork
Install toolchain
Backup calibration
✓ Ready to build
```

### **Week 1 End (Phase A)**
```
4 cuts implemented
Firmware compiled
Battery chirps... wait, we didn't add audio yet (it's Phase B)
Calibration error < stock ✓
All tests pass ✓
```

### **Week 3 End (Phase B)**
```
3 more cuts done
Web GUI loads configuration ✓
Adjust slider → Firmware updates ✓
Battery drops: "Chirp Chirp" at 25% ✓
Battery drops: "Chirp Chirp Chirp" at 5% ✓
2-hour test: no hangs ✓
100+ commands: all complete ✓
```

### **Week 4 End (Phase C, optional)**
```
3 cosmetic cuts done
Settings survive reboot ✓
Full integration test: explore → dock → charge → release ✓
Production ready ✓
```

---

## **CLI Agent's Role**

Your job is to:

1. **Execute the implementation runbook** (day-by-day)
2. **Follow each cut exactly** from FIRMWARE_CUSTOM_DESIGN.md
3. **Compile and test after every phase** (not just at the end)
4. **Log results** in markdown for human review
5. **Pass all validation gates** before proceeding to next phase
6. **Escalate immediately if** compilation fails, tests fail, or behavior is unexpected
7. **Document workarounds** for any non-standard issues
8. **Provide daily summaries** of progress

---

## **Quick Start**

### **For CLI Agent Starting Now:**

```bash
# 1. Read these documents IN ORDER
1. FIRMWARE_CUSTOM_DESIGN.md (understand the 10 cuts)
2. FIRMWARE_WEB_CONFIG.md (understand configuration system)
3. FIRMWARE_AUDIO_ALERTS.md (understand audio alerts)
4. FIRMWARE_IMPLEMENTATION_RUNBOOK.md (follow day-by-day)

# 2. Start Day 1
cd /path/to/bittle-custom-fw
git checkout -b phase-a-safety

# 3. Apply Cut #1
# Edit: OpenCat.h:80
# Change: #define DATE "260820" → #define DATE "251121"

# 4. Commit
git add OpenCat.h
git commit -m "Cut #1: Pin version to 251121"

# 5. Continue with Day 1 steps from runbook

# 6. Log progress
./log_progress.sh "Day 1: Cut #1 applied, ready for Cut #2"
```

---

## **All Documents in One Place**

📁 **Complete Firmware Design Suite:**
1. **FIRMWARE_CUSTOM_DESIGN.md** (10 cuts, detailed code)
2. **FIRMWARE_WEB_CONFIG.md** (configuration system)
3. **FIRMWARE_AUDIO_ALERTS.md** (battery alerts + voice)
4. **FIRMWARE_IMPLEMENTATION_RUNBOOK.md** (day-by-day for CLI agent)
5. **FIRMWARE_CUTS_QUICK_REF.md** (quick lookup)
6. **FIRMWARE_RESET_MAPPING.md** (problem → solution)
7. **FIRMWARE_COMPLETE_SUMMARY.md** (this document)

**Total:** ~400 KB of detailed design, ready to build.

---

## **Next Steps**

### **For Human (Jon):**
1. ✅ Review this summary (FIRMWARE_COMPLETE_SUMMARY.md)
2. ✅ Review FIRMWARE_CUSTOM_DESIGN.md (understand philosophy + 10 cuts)
3. ✅ Review FIRMWARE_WEB_CONFIG.md (understand configuration system)
4. ✅ Decide: **Start Phase A now or after calibration?**
5. ✅ Prepare hardware (USB cable, serial terminal, backup calibration)
6. ✅ Pass to CLI agent with FIRMWARE_IMPLEMENTATION_RUNBOOK.md

### **For CLI Agent:**
1. Read the 4 main documents (in order above)
2. Follow FIRMWARE_IMPLEMENTATION_RUNBOOK.md day-by-day
3. Apply each cut exactly as specified
4. Compile and test after every phase
5. Log all results, escalate if problems
6. Deliver final firmware + test logs

---

**All design complete. Ready to build. 🚀**

