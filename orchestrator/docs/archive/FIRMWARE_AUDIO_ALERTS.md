> **Archived 2026-09-02.** Superseded by [design/VOICE_RELAY_BRIEF.md](../design/VOICE_RELAY_BRIEF.md); kept for history. Details here no longer match the code.

# Audio Alerts & Voice System

**Status:** Designed, Phase B ready (chirps), Phase C ready (voice TTS)  
**Hardware:** Piezo buzzer (firmware `b` token) + MAX98357A amplifier + INMP441 mic  
**Integration:** Battery monitoring → chirp events → voice announcements (optional)

---

## **Audio Architecture**

```
BiBoard Battery Monitor
    ↓ (every 1 second, reads ADC)
    ├─ Is battery below threshold?
    │   └─ Yes: Trigger chirp event
    │   
    ├─ Event: Battery 23%
    │   ├─ (Phase B) Chirp 1× (frequency, volume via config)
    │   └─ (Phase C) Voice: "Battery 23 percent"
    │
    └─ Event: Battery 4%
        ├─ Chirp 3× (critical alert)
        └─ Voice: "Critical: battery 4 percent, entering rest mode"

All alerts are configurable:
  ✅ Enable/disable alerts
  ✅ Set thresholds (default: 25%, 15%, 5%)
  ✅ Chirp volume (0-100%)
  ✅ Chirp frequency (Hz, default 1000Hz)
  ✅ Voice enable (Phase C, when TTS ready)
```

---

## **Phase B: Chirp Alerts (Ready Now)**

### **Chirp Behavior**

```
Battery Threshold Detection:

  25% threshold:
    └─ 1 chirp (200ms)
    └─ Neutral alert
    
  15% threshold:
    └─ 2 chirps (200ms + 100ms gap + 200ms)
    └─ Warning
    
  5% threshold:
    └─ 3 chirps (urgent)
    └─ Critical: "rest" action imminent
```

### **Audio Generation Code**

```cpp
// firmware/audio.cpp

#define SPEAKER_PIN 12        // GPIO12 on BiBoard
#define BUZZER_PIN 33         // Some BiBoards have dual output

struct AudioAlert {
  uint8_t battery_pct;
  uint8_t num_chirps;
  uint16_t chirp_duration_ms;
  uint16_t gap_duration_ms;
  bool triggered_this_level;  // Debounce: only chirp once per level
};

AudioAlert alerts[] = {
  {25, 1, 200, 100, false},   // Low
  {15, 2, 200, 100, false},   // Warning
  {5,  3, 200, 100, false},   // Critical
};

void checkBatteryAndChirp() {
  uint8_t battery_pct = readBatteryPercentage();
  
  // Check each threshold
  for (int i = 0; i < 3; i++) {
    AudioAlert* alert = &alerts[i];
    
    if (battery_pct <= alert->battery_pct && !alert->triggered_this_level) {
      // Trigger chirp for this level
      playChirp(alert->num_chirps, alert->chirp_duration_ms, alert->gap_duration_ms);
      alert->triggered_this_level = true;
      
      // Report to adapter
      printf("[battery_alert] level_%d pct=%d chirps=%d\n",
             i, battery_pct, alert->num_chirps);
      
    } else if (battery_pct > alert->battery_pct) {
      // Reset trigger when battery recovers above threshold
      alert->triggered_this_level = false;
    }
  }
}

void playChirp(uint8_t num_chirps, uint16_t duration_ms, uint16_t gap_ms) {
  if (!config.audio.battery_warnings_enabled) return;
  
  for (int i = 0; i < num_chirps; i++) {
    // Play tone
    tone(SPEAKER_PIN, 
         config.audio.chirp_frequency, 
         duration_ms,
         config.audio.chirp_volume);  // 0-100 mapped to volume
    
    // Wait for tone to finish
    delay(duration_ms);
    
    // Gap between chirps (except after last one)
    if (i < num_chirps - 1) {
      delay(gap_ms);
    }
  }
}

// Wrapper for tone() with volume control
void tone(uint8_t pin, uint16_t frequency, uint16_t duration_ms, uint8_t volume_0_100) {
  // tone() doesn't have volume control, so simulate via duty cycle
  // OR use PWM directly
  
  uint32_t period_us = 1000000 / frequency;
  uint32_t on_time_us = (period_us * volume_0_100) / 100;
  uint32_t off_time_us = period_us - on_time_us;
  
  uint32_t end_time = millis() + duration_ms;
  
  while (millis() < end_time) {
    digitalWrite(pin, HIGH);
    delayMicroseconds(on_time_us);
    digitalWrite(pin, LOW);
    delayMicroseconds(off_time_us);
  }
}
```

### **Configuration (Already Defined)**

```json
{
  "audio": {
    "battery_warnings_enabled": true,
    "battery_warning_thresholds": [25, 15, 5],
    "chirp_volume": 80,              // 0-100%
    "chirp_frequency_hz": 1000,      // Hz (standard tone)
    "voice_battery_percentage": true,  // Phase C: enable voice
    "voice_enabled": false,           // Phase C: when TTS ready
    "voice_volume": 75
  }
}
```

---

## **Phase C: Voice Announcements (Future)**

### **Voice System Architecture**

```
BiBoard triggers voice event
    ↓
Adapter receives battery alert
    ↓
Adapter requests TTS from Eleven Labs
    ├─ "Your battery is 23 percent"
    └─ "Critical: battery 4 percent"
    ↓
Adapter receives audio MP3
    ↓
Adapter sends to BiBoard via WebSocket (binary frame)
    ↓
BiBoard MAX98357A amplifier streams audio
    └─ Speaker plays announcement
```

### **Eleven Labs Integration**

```python
# adapter/voice_alerts.py

import requests

ELEVEN_LABS_API_KEY = os.environ.get('ELEVEN_LABS_API_KEY')
VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel (female, clear)

async def announce_battery_status(battery_pct: int, is_critical: bool):
    """Generate and play voice announcement of battery level."""
    
    if not config.audio.voice_enabled:
        return
    
    # Generate message
    if is_critical:
        message = f"Critical: battery {battery_pct} percent, entering rest mode"
    else:
        message = f"Your battery is {battery_pct} percent"
    
    # Request TTS from Eleven Labs
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_LABS_API_KEY,
        "Content-Type": "application/json"
    }
    body = {
        "text": message,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    
    response = requests.post(url, json=body, headers=headers)
    
    if response.status_code == 200:
        audio_data = response.content  # MP3 bytes
        
        # Send to BiBoard for playback
        await self.send_audio_to_bittle(audio_data)
    else:
        logger.error(f"TTS failed: {response.status_code}")

async def send_audio_to_bittle(audio_data: bytes):
    """Stream audio to BiBoard for playback via MAX98357A."""
    
    # Chunk audio and send via WebSocket binary frames
    chunk_size = 1024
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i+chunk_size]
        
        # Send binary frame with type=audio
        await self.ws.send_binary({
            "type": "audio_chunk",
            "sequence": i // chunk_size,
            "data": base64.b64encode(chunk).decode()
        })
        
        # Rate limit: 50ms between chunks (prevents buffer overflow)
        await asyncio.sleep(0.05)
    
    # Send end-of-audio marker
    await self.ws.send_binary({
        "type": "audio_end"
    })
```

### **Firmware Audio Playback**

```cpp
// firmware/audio_playback.cpp

#define AUDIO_BUFFER_SIZE 8192

class AudioPlayer {
  uint8_t audio_buffer[AUDIO_BUFFER_SIZE];
  uint16_t write_pos = 0;
  uint16_t read_pos = 0;
  bool is_playing = false;
  
public:
  void onAudioChunk(const uint8_t* data, size_t len) {
    // Write incoming audio data to circular buffer
    for (size_t i = 0; i < len && write_pos < AUDIO_BUFFER_SIZE; i++) {
      audio_buffer[write_pos++] = data[i];
    }
    
    // Start playback if buffer has data
    if (!is_playing && write_pos > 512) {
      startPlayback();
    }
  }
  
  void onAudioEnd() {
    // Signal end of stream
    // Playback continues until buffer drained
    is_playing = false;
  }
  
  void startPlayback() {
    is_playing = true;
    
    // Setup I2S audio output
    // - MCLK: GPIO0
    // - BCK:  GPIO26
    // - WS:   GPIO25
    // - DIN:  GPIO14 (to MAX98357A)
    
    i2s_config_t i2s_config = {
      .mode = I2S_MODE_MASTER | I2S_MODE_TX,
      .sample_rate = 16000,  // Eleven Labs default
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 8,
      .dma_buf_len = 512,
      .use_apll = false,
      .tx_desc_auto_clear = true,
      .fixed_mclk = 0
    };
    
    i2s_driver_install(I2S_NUM_0, &i2s_config, 0, NULL);
    i2s_set_pin(I2S_NUM_0, &pin_config);
    i2s_start(I2S_NUM_0);
  }
  
  void playbackTask() {
    // Background task: drain buffer, stream audio
    while (is_playing || read_pos < write_pos) {
      size_t bytes_to_play = write_pos - read_pos;
      
      if (bytes_to_play > 0) {
        size_t written;
        i2s_write(I2S_NUM_0, 
                  &audio_buffer[read_pos], 
                  bytes_to_play, 
                  &written, 
                  portMAX_DELAY);
        
        read_pos += written;
      } else {
        delay(10);  // Wait for more data
      }
    }
    
    i2s_stop(I2S_NUM_0);
    is_playing = false;
  }
};

AudioPlayer audio_player;

// WebSocket receive handler
void onWebSocketMessage(uint8_t* payload, size_t len) {
  if (/* message type == audio_chunk */) {
    uint8_t* audio_data = decode_base64(payload);
    audio_player.onAudioChunk(audio_data, len);
  } else if (/* message type == audio_end */) {
    audio_player.onAudioEnd();
  }
}
```

---

## **Integration Timeline**

### **Phase B (Now): Chirps Only**
```
✅ Week 1:
   - Implement playChirp() in firmware
   - Configure battery thresholds
   - Test: battery drops, hear chirps
   - Volume control via GUI slider
   
✅ Week 2:
   - Integration tests (full cycle)
   - Verify no impact on motion
   - Stress test: 100+ battery cycles
```

### **Phase C (4-6 weeks): Full Voice**
```
📋 Week 1:
   - Eleven Labs API integration (adapter)
   - TTS request/response flow
   
📋 Week 2:
   - I2S audio output (firmware)
   - MAX98357A initialization
   - Binary WebSocket streaming
   
📋 Week 3:
   - End-to-end testing
   - Audio quality (sample rate, volume)
   - Voice messages recorded + tested
   
📋 Week 4:
   - Handle network failures (no TTS available)
   - Fallback: chirp only
   - Cost monitoring (Eleven Labs $0.30/month)
```

---

## **Battery Monitoring Loop**

### **Firmware Battery Check**

```cpp
// firmware/battery_monitor.cpp

void batteryMonitorTask(void* param) {
  TickType_t last_check = xTaskGetTickCount();
  
  while (true) {
    // Check every 1 second
    if ((xTaskGetTickCount() - last_check) > 1000) {
      uint8_t battery_pct = readBatteryPercentage();
      
      // Check alerts
      checkBatteryAndChirp();
      
      // Check low-battery action
      if (battery_pct <= config.motion.low_battery_threshold &&
          config.motion.low_battery_action == "rest") {
        executeSkill(REST);
        print("[battery] Low battery, entering rest mode\n");
      }
      
      last_check = xTaskGetTickCount();
    }
    
    vTaskDelay(100 / portTICK_PERIOD_MS);
  }
}
```

### **Adapter Battery Event Handling**

```python
# adapter/battery_monitor.py

async def handle_battery_alert(event):
    """
    Receives battery alert from firmware.
    Event format: [battery_alert] level_0 pct=23 chirps=1
    """
    
    battery_pct = event.get('pct')
    num_chirps = event.get('chirps')
    
    logger.info(f"🔋 Battery {battery_pct}% (chirps: {num_chirps})")
    
    # Phase C: Voice announcement
    if config.audio.voice_battery_percentage:
        await announce_battery_status(battery_pct, is_critical=(num_chirps >= 3))
    
    # Persist to history
    self.battery_history.append({
        'timestamp': datetime.utcnow(),
        'battery_pct': battery_pct,
        'alert_level': num_chirps
    })
    
    # Trigger rest if critical
    if battery_pct <= config.motion.low_battery_threshold:
        logger.warning(f"⚠️ Battery critical ({battery_pct}%), rest action triggered")
        # Orchestrator will handle dock + charge cycle
```

---

## **Audio Configuration Flow**

```
User adjusts chirp volume in Web GUI
    ↓
GUI: POST /api/config/audio/chirp_volume {value: 60}
    ↓
Adapter validates (0-100)
    ↓
Adapter: T_CONFIG_SET audio chirp_volume 60
    ↓
Firmware receives, updates config.audio.chirp_volume = 60
    ↓
Firmware saves to NVS (persists on reboot)
    ↓
Next battery alert uses new volume
```

---

## **Testing Chirp Alerts**

### **Manual Test**

```
1. Set battery threshold to 95%
   POST /api/config/motion/low_battery_threshold_pct {value: 95}

2. Watch power indicator (will trigger immediately)

3. Hear 1 chirp (25% level)
   - Check firmware log: "[battery_alert] level_0 pct=95"

4. Set threshold to 50%
   POST /api/config/motion/low_battery_threshold_pct {value: 50}

5. Hear 2 chirps (15% level, battery now below 50%)

6. Set threshold to 5% (original)
   POST /api/config/motion/low_battery_threshold_pct {value: 5}

7. Verify no more alerts until battery drops to 25% naturally
```

### **Integration Test**

```
Run full charge cycle:
  1. Dock charges from 1% to 100%
  2. Listen for no alerts (all above thresholds)
  3. Start exploration
  4. Monitor for chirps at 25%, 15%, 5%
  5. Verify dog rests at 5%
  6. Dock charges again
```

---

## **Cost Analysis (Phase C)**

### **Eleven Labs Pricing**

```
Free tier: 10,000 characters/month

Our usage:
  • "Battery 23 percent" = ~20 chars
  • Once per battery level (~5 unique levels) = 100 chars/cycle
  • Full charge cycle = 1 call (100 chars)
  
Cost per dog/month:
  • Heavy use (2 dogs, 10 cycles/day): ~500 chars = FREE
  • Moderate use (5 cycles/day): ~250 chars = FREE
  • Light use (1 cycle/day): ~50 chars = FREE
  
Cost: $0/month for most users
Max: $0.39/month if over 10k chars (Starter plan)
```

---

## **Fallback Behavior**

If TTS fails (network down, API error):

```cpp
async def handle_battery_alert(event):
    battery_pct = event.get('pct')
    
    if config.audio.voice_battery_percentage:
        try:
            await announce_battery_status(battery_pct)
        except Exception as e:
            logger.warning(f"TTS failed: {e}, falling back to chirps")
            # Firmware already played chirps
            # No additional action needed
```

Firmware always plays chirps (local), so voice is optional layer.

---

## **Default Thresholds**

```json
{
  "battery_warning_thresholds": [25, 15, 5]
}
```

| Threshold | Alert | Action |
|-----------|-------|--------|
| **25%** | 1 chirp | Gentle reminder, can continue exploring |
| **15%** | 2 chirps | Stronger reminder, consider docking soon |
| **5%** | 3 chirps | CRITICAL, rest action imminent |

---

## **Customization Examples**

### **Example 1: Silent Mode**
```json
{
  "battery_warnings_enabled": false
}
```
No chirps, no voice. Battery low triggers rest silently.

### **Example 2: Loud Warnings**
```json
{
  "chirp_volume": 100,
  "chirp_frequency_hz": 2000,
  "battery_warning_thresholds": [40, 20, 5]
}
```
Loud, high-pitched chirps at more thresholds.

### **Example 3: Voice + Chirps**
```json
{
  "battery_warnings_enabled": true,
  "voice_enabled": true,
  "voice_battery_percentage": true,
  "chirp_volume": 60,
  "voice_volume": 75
}
```
Both audio alert and voice announcement.

---

**Audio system is fully designed and ready for Phase B implementation.** 🔊

