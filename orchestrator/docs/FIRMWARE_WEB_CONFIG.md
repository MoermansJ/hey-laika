# Firmware Web Configuration System

**Status:** Design ready for implementation  
**Integration:** Web GUI ↔ Adapter ↔ BiBoard (over REST API)  
**Storage:** Persistent NVS (survives reboot)  
**Defaults:** Sensible + safe

---

## **Configuration Hierarchy**

```
┌─────────────────────────────┐
│   Web GUI (React/HTML)      │  User configures via web interface
│   ↓ Submit config changes   │
├─────────────────────────────┤
│   Adapter (Python Flask)    │  API layer: validates, stores, syncs
│   POST /api/config/{key}    │
│   GET /api/config           │
│   ↓                         │
├─────────────────────────────┤
│   BiBoard Firmware          │  Reads config, applies settings
│   T_CONFIG_SET token        │  Persists to NVS
│   NVS storage               │
└─────────────────────────────┘
```

---

## **Configuration Schema**

### **Safety & Motion Settings**

```json
{
  "motion": {
    "imu_reflexes_enabled": true,          // Auto-flip/knock-recovery
    "imu_reflex_type": "flip_only",        // "flip_only" | "full" | "none"
    "low_battery_threshold_pct": 5,        // When to stop motion (0-20%)
    "low_battery_action": "rest",          // "rest" | "report_only"
    "transform_speed": 1.0,                // Stand/lay animation speed (0.5-2.0)
    "max_tilt_degrees": 45                 // Safety cutoff (abort if tilted > this)
  }
```

### **Audio & Voice Settings**

```json
{
  "audio": {
    "battery_warnings_enabled": true,      // Chirp + voice at thresholds
    "battery_warning_thresholds": [25, 15, 5],  // % battery → alert
    "voice_battery_percentage": true,      // "Battery 23 percent"
    "chirp_volume": 80,                    // 0-100
    "chirp_frequency_hz": 1000,            // Beep pitch
    "voice_enabled": true,                 // TTS announcements (Phase 3)
    "voice_volume": 75                     // 0-100
  }
```

### **Autonomous Behavior Settings**

```json
{
  "behavior": {
    "auto_wander_enabled": false,          // z token activation
    "wander_idle_timeout_sec": 30,         // How long before wandering
    "personality_enabled": true,           // Behavior tree active
    "exploration_mode": "frontier"         // "frontier" | "grid" | "random"
  }
```

### **Sensing & Processing**

```json
{
  "sensing": {
    "imu_sample_rate_hz": 50,              // IMU polling rate
    "collision_sensitivity": "normal",     // "sensitive" | "normal" | "relaxed"
    "camera_enabled": false,               // Future: Grove Vision AI V2
    "lidar_enabled": false,                // Future: distance sensing
    "touch_enabled": true                  // Back touch sensor
  }
```

---

## **Adapter API Endpoints**

### **Get All Configuration**

```
GET /api/config
Response:
{
  "motion": { ... },
  "audio": { ... },
  "behavior": { ... },
  "sensing": { ... },
  "defaults": { ... },
  "last_updated": "2026-08-31T10:15:30Z"
}
```

### **Get Single Setting**

```
GET /api/config/motion/imu_reflexes_enabled
Response:
{
  "key": "imu_reflexes_enabled",
  "value": true,
  "type": "boolean",
  "default": true,
  "description": "Enable auto-flip and knock-recovery"
}
```

### **Update Setting**

```
POST /api/config/{section}/{key}
Body:
{
  "value": false
}

Response:
{
  "status": "success",
  "key": "imu_reflexes_enabled",
  "old_value": true,
  "new_value": false,
  "synced_to_firmware": true
}
```

### **Reset to Defaults**

```
POST /api/config/reset
Body: { "section": "motion" }  // or "all"

Response:
{
  "status": "success",
  "reset_keys": ["imu_reflexes_enabled", "low_battery_threshold_pct"],
  "synced_to_firmware": true
}
```

### **Import/Export Configuration**

```
GET /api/config/export
Response: JSON file (gait_config.json)

POST /api/config/import
Body: (file upload)
Response: { "status": "success", "keys_imported": 12 }
```

---

## **Web GUI Layout**

### **Configuration Panel (React Component)**

```
┌─────────────────────────────────────────┐
│  🐕 Bittle Configuration                │
├─────────────────────────────────────────┤
│                                         │
│  📋 MOTION SETTINGS                     │
│  ├─ ☑ IMU Auto-Recovery                │
│  │  └─ Mode: [Flip Only ▼]            │
│  ├─ Low Battery Action                 │
│  │  └─ Threshold: 5% [●────] 20%      │
│  │  └─ Action: [Rest ▼]               │
│  ├─ Transform Speed                    │
│  │  └─ [○───●─────] 1.0x              │
│  └─ Max Tilt Angle: 45°               │
│                                         │
│  🔊 AUDIO & ALERTS                      │
│  ├─ ☑ Battery Warnings                 │
│  │  └─ Thresholds: 25% • 15% • 5%    │
│  ├─ ☑ Voice Percentage Announce       │
│  │  └─ "Battery 23 percent"           │
│  ├─ Chirp Volume: [●──────] 80%       │
│  └─ Voice Volume: [●──────] 75%       │
│                                         │
│  🤖 BEHAVIOR                            │
│  ├─ ☐ Auto-Wander                      │
│  ├─ Personality Enabled: ☑             │
│  └─ Exploration: [Frontier ▼]         │
│                                         │
│  📡 SENSING                             │
│  ├─ IMU Rate: 50 Hz                    │
│  ├─ Collision: [Normal ▼]             │
│  ├─ ☐ Camera (future)                  │
│  └─ ☑ Touch Sensor                     │
│                                         │
│  [Reset to Defaults] [Export] [Import] │
│  [🔄 Sync to Device]  ✓ In Sync        │
│                                         │
└─────────────────────────────────────────┘
```

### **Key UI Components**

#### **Toggle (Boolean)**
```jsx
<ConfigToggle 
  label="IMU Auto-Recovery"
  section="motion"
  key="imu_reflexes_enabled"
  value={true}
  onChange={(value) => updateConfig(...)}
/>
```

#### **Select (Enum)**
```jsx
<ConfigSelect 
  label="Low Battery Action"
  options={["rest", "report_only"]}
  value="rest"
  onChange={(value) => updateConfig(...)}
/>
```

#### **Slider (Range)**
```jsx
<ConfigSlider 
  label="Low Battery Threshold"
  min={0}
  max={20}
  value={5}
  unit="%"
  onChange={(value) => updateConfig(...)}
/>
```

#### **Multi-Select (Array)**
```jsx
<ConfigMultiSelect 
  label="Battery Warning Thresholds"
  options={[25, 15, 10, 5]}
  values={[25, 15, 5]}
  unit="%"
  onChange={(values) => updateConfig(...)}
/>
```

---

## **Default Configuration Values**

```json
{
  "motion": {
    "imu_reflexes_enabled": true,
    "imu_reflex_type": "flip_only",
    "low_battery_threshold_pct": 5,
    "low_battery_action": "rest",
    "transform_speed": 1.0,
    "max_tilt_degrees": 45
  },
  "audio": {
    "battery_warnings_enabled": true,
    "battery_warning_thresholds": [25, 15, 5],
    "voice_battery_percentage": true,
    "chirp_volume": 80,
    "chirp_frequency_hz": 1000,
    "voice_enabled": false,  // Phase 3: enable when TTS ready
    "voice_volume": 75
  },
  "behavior": {
    "auto_wander_enabled": false,
    "wander_idle_timeout_sec": 30,
    "personality_enabled": true,
    "exploration_mode": "frontier"
  },
  "sensing": {
    "imu_sample_rate_hz": 50,
    "collision_sensitivity": "normal",
    "camera_enabled": false,
    "lidar_enabled": false,
    "touch_enabled": true
  }
}
```

---

## **Firmware Configuration Storage (NVS)**

### **Memory Layout**

```
Namespace: "bittle_config"

Key: "motion_imu_reflex" → Value: 1 (true)
Key: "motion_bat_thr" → Value: 5 (int)
Key: "audio_warnings" → Value: 1 (true)
Key: "audio_thresh" → Value: "25,15,5" (string)
Key: "audio_chirp_vol" → Value: 80 (int)
...

Total: ~2KB NVS (out of 8KB config partition)
```

### **Firmware Configuration Struct**

```cpp
// firmware/config.h

struct MotionConfig {
  bool imu_reflexes_enabled = true;
  uint8_t imu_reflex_type = FLIP_ONLY;  // enum
  uint8_t low_battery_threshold = 5;     // 0-20%
  uint8_t low_battery_action = REST;     // enum
  float transform_speed = 1.0;
  uint8_t max_tilt_degrees = 45;
};

struct AudioConfig {
  bool battery_warnings_enabled = true;
  uint8_t battery_thresholds[3] = {25, 15, 5};
  bool voice_battery_pct = true;
  uint8_t chirp_volume = 80;             // 0-100
  uint16_t chirp_frequency = 1000;       // Hz
  bool voice_enabled = false;            // Phase 3
  uint8_t voice_volume = 75;
};

struct BehaviorConfig {
  bool auto_wander_enabled = false;
  uint16_t wander_timeout_sec = 30;
  bool personality_enabled = true;
  uint8_t exploration_mode = FRONTIER;   // enum
};

struct SensingConfig {
  uint8_t imu_rate_hz = 50;
  uint8_t collision_sensitivity = NORMAL;  // enum
  bool camera_enabled = false;
  bool lidar_enabled = false;
  bool touch_enabled = true;
};

struct Config {
  MotionConfig motion;
  AudioConfig audio;
  BehaviorConfig behavior;
  SensingConfig sensing;
  uint32_t checksum = 0;  // Detect corruption
  uint32_t last_update_timestamp = 0;
};
```

---

## **Adapter Configuration Manager**

```python
# adapter/config_manager.py

class ConfigManager:
    def __init__(self, nv_storage_file="config/bittle_config.json"):
        self.config = self.load_defaults()
        self.load_from_storage(nv_storage_file)
        self.synced_to_firmware = False
    
    def load_defaults(self):
        return {
            "motion": {
                "imu_reflexes_enabled": True,
                "imu_reflex_type": "flip_only",
                "low_battery_threshold_pct": 5,
                "low_battery_action": "rest",
                "transform_speed": 1.0,
                "max_tilt_degrees": 45
            },
            # ... rest of schema
        }
    
    def get_setting(self, section, key):
        """Get a single setting."""
        try:
            return self.config[section][key]
        except KeyError:
            return self.load_defaults()[section][key]
    
    def set_setting(self, section, key, value):
        """Update a setting, validate, persist, sync to firmware."""
        # 1. Validate
        if not self.validate(section, key, value):
            raise ValueError(f"Invalid value for {section}.{key}: {value}")
        
        # 2. Store old value
        old_value = self.config[section][key]
        
        # 3. Update
        self.config[section][key] = value
        
        # 4. Persist to disk
        self.save_to_storage()
        
        # 5. Sync to firmware
        self.sync_to_firmware(section, key, value)
        
        return {
            "status": "success",
            "key": f"{section}.{key}",
            "old_value": old_value,
            "new_value": value,
            "synced_to_firmware": True
        }
    
    def sync_to_firmware(self, section, key, value):
        """Send config update to BiBoard."""
        # Use T_CONFIG_SET token
        command = f"T_CONFIG_SET {section} {key} {value}"
        result = self.ws.send_command(command)
        return result
    
    def sync_all_to_firmware(self):
        """Full config push on startup."""
        for section in self.config:
            for key, value in self.config[section].items():
                self.sync_to_firmware(section, key, value)
    
    def validate(self, section, key, value):
        """Type and range checking."""
        schema = self.get_schema(section, key)
        
        if schema["type"] == "boolean":
            return isinstance(value, bool)
        elif schema["type"] == "int":
            return isinstance(value, int) and schema["min"] <= value <= schema["max"]
        elif schema["type"] == "float":
            return isinstance(value, float) and schema["min"] <= value <= schema["max"]
        elif schema["type"] == "enum":
            return value in schema["options"]
        
        return False
    
    def get_schema(self, section, key):
        """Metadata for a setting (for GUI rendering)."""
        schemas = {
            "motion": {
                "imu_reflexes_enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable auto-flip and knock-recovery"
                },
                "low_battery_threshold_pct": {
                    "type": "int",
                    "min": 0,
                    "max": 20,
                    "default": 5,
                    "unit": "%",
                    "description": "Battery level triggers rest action"
                },
                # ... more keys
            }
            # ... more sections
        }
        
        return schemas[section][key]
```

---

## **Firmware Configuration Token**

### **New Token: T_CONFIG_SET**

```
Format: T_CONFIG_SET <section> <key> <value>

Examples:
  T_CONFIG_SET motion imu_reflexes_enabled 1
  T_CONFIG_SET motion low_battery_threshold_pct 5
  T_CONFIG_SET audio chirp_volume 80
  T_CONFIG_SET audio battery_thresholds "25,15,5"

Response:
  [config] motion.imu_reflexes_enabled = 1
  [config] Saved to NVS, will persist on reboot
```

### **Firmware Config Handler**

```cpp
// firmware/config_token.h

void processConfigToken(byte* buffer, size_t len) {
  // Parse: T_CONFIG_SET section key value
  char section[32], key[32], value[128];
  
  if (sscanf((char*)buffer, "T_CONFIG_SET %s %s %s", 
      section, key, value) != 3) {
    print("Error parsing config token\n");
    return;
  }
  
  // Route to section
  if (strcmp(section, "motion") == 0) {
    setMotionConfig(key, value);
  } else if (strcmp(section, "audio") == 0) {
    setAudioConfig(key, value);
  } else if (strcmp(section, "behavior") == 0) {
    setBehaviorConfig(key, value);
  } else if (strcmp(section, "sensing") == 0) {
    setSensingConfig(key, value);
  }
  
  // Persist to NVS
  saveConfigToNVS();
  
  // Confirm
  printf("[config] %s.%s = %s\n", section, key, value);
}

void setMotionConfig(const char* key, const char* value) {
  if (strcmp(key, "imu_reflexes_enabled") == 0) {
    config.motion.imu_reflexes_enabled = (atoi(value) == 1);
  } else if (strcmp(key, "low_battery_threshold_pct") == 0) {
    config.motion.low_battery_threshold = atoi(value);
  } else if (strcmp(key, "transform_speed") == 0) {
    config.motion.transform_speed = atof(value);
  }
  // ... more keys
}
```

---

## **Audio Alert Integration**

### **Battery Warning Thresholds**

```
When battery drops below configured thresholds:
  25%: Chirp 1× (mild reminder)
  15%: Chirp 2× (stronger reminder)
  5%:  Chirp 3× (critical, rest imminent)

When voice enabled (Phase 3):
  "Your battery is 23 percent"
  "Battery at 14 percent"
  "Critical: battery 4 percent, entering rest mode"
```

### **Chirp Implementation**

```cpp
// firmware/audio.h

void chirpBattery(uint8_t battery_pct) {
  uint8_t num_chirps = 1;
  
  if (battery_pct <= 5) {
    num_chirps = 3;  // Critical
  } else if (battery_pct <= 15) {
    num_chirps = 2;  // Warning
  } else if (battery_pct <= 25) {
    num_chirps = 1;  // Notice
  } else {
    return;  // No chirp
  }
  
  for (int i = 0; i < num_chirps; i++) {
    tone(SPEAKER_PIN, config.audio.chirp_frequency, 200);  // 200ms beep
    delay(100);  // Gap between chirps
  }
}

void announceVoice(const char* message) {
  if (!config.audio.voice_enabled) return;
  
  // Phase 3: Call TTS service, stream audio
  // For now: just serial log
  printf("[voice] %s\n", message);
}
```

---

## **Phase Implementation**

### **Phase A: Core Configuration**
```
✅ Cut #1-4 + basic config system
✅ Motion settings (reflexes, low battery)
✅ Transform speed
✅ Persist to NVS
✅ Adapter API endpoints
✅ Web GUI panels
```

### **Phase B: Audio Integration**
```
✅ Chirp generation
✅ Battery threshold monitoring
✅ Voice percentage announce (logging only)
✅ Chirp volume control
✅ GUI for audio settings
```

### **Phase C: Voice (TTS)**
```
📋 Eleven Labs TTS integration
📋 "Battery 23 percent" announcement
📋 Full voice feedback system
📋 Network integration (requires cloud)
```

---

## **Configuration Flow (Example)**

```
1. User opens Web GUI
   └─ Loads current config from /api/config

2. User changes "Low Battery Threshold" from 5% to 8%
   └─ GUI shows slider update

3. User clicks "Apply"
   └─ POST /api/config/motion/low_battery_threshold_pct
      Body: {"value": 8}

4. Adapter validates, stores, syncs
   └─ Sends T_CONFIG_SET motion low_battery_threshold_pct 8
   └─ Firmware saves to NVS
   └─ Confirms: "[config] motion.low_battery_threshold_pct = 8"

5. Dog reboots
   └─ Firmware loads config from NVS (8% threshold persists)

6. Battery drops below 8%
   └─ Firmware chirps 2×
   └─ (If voice enabled) announces "Battery 7 percent"
   └─ Prepares rest action per "low_battery_action" setting
```

---

## **Storage & Persistence**

### **Files**

```
Adapter (Python):
  └─ config/bittle_config.json (human-readable backup)

BiBoard (Firmware):
  └─ NVS partition "bittle_config" (survives reboot)
  
Web GUI:
  └─ localStorage (browser-side, for quick UX feedback)
```

### **Sync Strategy**

```
On Startup:
  1. Adapter loads from bittle_config.json
  2. Adapter syncs all settings to firmware
  3. Firmware loads/overwrites its NVS copy
  
On Config Change:
  1. GUI → Adapter (via REST API)
  2. Adapter validates
  3. Adapter saves to bittle_config.json
  4. Adapter sends T_CONFIG_SET to firmware
  5. Firmware saves to NVS
  6. Adapter confirms sync complete
  
On Reboot (Firmware):
  1. Firmware loads from NVS
  2. Applies settings immediately
  3. Ready to go (no network needed)
```

---

## **Testing Checklist**

- [ ] Config endpoints return correct schema
- [ ] Setting update persists across adapter restart
- [ ] Setting update persists across firmware reboot
- [ ] Invalid values rejected with clear error
- [ ] GUI renders all settings correctly
- [ ] Toggle, slider, select, multi-select all work
- [ ] Reset to defaults works
- [ ] Export/import configuration works
- [ ] Audio chirps play at correct thresholds
- [ ] Voice announcements (when Phase 3 ready)

---

## **GUI Component Stubs (React)**

```tsx
// components/ConfigPanel.tsx

export function ConfigPanel() {
  const [config, setConfig] = useState(null);
  const [synced, setSynced] = useState(true);

  useEffect(() => {
    fetchConfig();
  }, []);

  async function fetchConfig() {
    const res = await fetch('/api/config');
    setConfig(await res.json());
  }

  async function updateSetting(section, key, value) {
    setSynced(false);
    const res = await fetch(`/api/config/${section}/${key}`, {
      method: 'POST',
      body: JSON.stringify({ value })
    });
    const result = await res.json();
    if (result.status === 'success') {
      setConfig(prev => ({
        ...prev,
        [section]: { ...prev[section], [key]: value }
      }));
      setSynced(true);
    }
  }

  return (
    <div className="config-panel">
      <h2>🐕 Bittle Configuration</h2>
      
      <section className="motion-settings">
        <h3>📋 Motion Settings</h3>
        
        <ConfigToggle
          label="IMU Auto-Recovery"
          value={config?.motion?.imu_reflexes_enabled}
          onChange={(v) => updateSetting('motion', 'imu_reflexes_enabled', v)}
        />
        
        <ConfigSlider
          label="Low Battery Threshold"
          min={0}
          max={20}
          value={config?.motion?.low_battery_threshold_pct}
          unit="%"
          onChange={(v) => updateSetting('motion', 'low_battery_threshold_pct', v)}
        />
        
        <ConfigSlider
          label="Transform Speed"
          min={0.5}
          max={2.0}
          step={0.1}
          value={config?.motion?.transform_speed}
          onChange={(v) => updateSetting('motion', 'transform_speed', v)}
        />
      </section>

      <section className="audio-settings">
        <h3>🔊 Audio & Alerts</h3>
        
        <ConfigToggle
          label="Battery Warnings"
          value={config?.audio?.battery_warnings_enabled}
          onChange={(v) => updateSetting('audio', 'battery_warnings_enabled', v)}
        />
        
        <ConfigMultiSelect
          label="Warning Thresholds"
          options={[5, 10, 15, 20, 25]}
          values={config?.audio?.battery_warning_thresholds}
          unit="%"
          onChange={(v) => updateSetting('audio', 'battery_warning_thresholds', v)}
        />
        
        <ConfigSlider
          label="Chirp Volume"
          min={0}
          max={100}
          value={config?.audio?.chirp_volume}
          unit="%"
          onChange={(v) => updateSetting('audio', 'chirp_volume', v)}
        />
      </section>

      {/* More sections... */}

      <div className="controls">
        <button onClick={() => fetchConfig()}>🔄 Reload</button>
        <button onClick={() => fetch('/api/config/reset', {method: 'POST'})}>
          Reset Defaults
        </button>
        <span className={synced ? 'synced' : 'syncing'}>
          {synced ? '✓ In Sync' : '⏳ Syncing...'}
        </span>
      </div>
    </div>
  );
}
```

---

**Configuration system is fully designed, ready for firmware + adapter implementation.** 🎯

