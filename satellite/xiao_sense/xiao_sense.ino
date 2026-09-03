// hey-laika satellite: XIAO ESP32S3 Sense = Laika's ears, eyes and mood light.
//
//  - PDM microphone -> 16 kHz mono int16 PCM -> UDP datagrams to the adapter
//    (4-byte big-endian sequence number + 320 samples = 20 ms per packet).
//    The adapter's ears.py segments utterances and runs whisper.
//  - OV2640 camera -> MJPEG over HTTP on port 80:  /stream (multipart),
//    /snap (one JPEG), / (status JSON). YOLO runs host-side (eyes.py).
//  - Grove Chainable RGB LED (P9813) on D2 (clock) / D3 (data): the mood
//    light. /led?r=&g=&b=&effect=solid|pulse|blink|off&periodMs=&brightness=
//    sets it; the adapter's mood.py owns what the colours mean.
//
// Wiring: powered from a spare Grove socket's VCC/GND on the BiBoard (meter
// the rail first, see docs/design/ARRIVAL_DAY_RUNBOOK.md). The LED's yellow
// wire (CI) goes to D2, white (DI) to D3, power from analog socket B. No
// data wires to the dog: everything rides the satellite's own WiFi.
//
// Build: arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3
//        --board-options "PSRAM=opi,PartitionScheme=default_8MB" satellite/xiao_sense
// Credentials: copy secrets.h.example to secrets.h.

#include <WiFi.h>
#include <WiFiUdp.h>
#include <driver/i2s.h>
#include <math.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "secrets.h"

// ---- tunables ---------------------------------------------------------------
static const int      SAMPLE_RATE      = 16000;
static const int      SAMPLES_PER_PKT  = 320;      // 20 ms
static const int      MIC_GAIN_SHIFT   = 3;        // x8; PDM mic is quiet
static const uint32_t STATUS_PERIOD_MS = 10000;
static const framesize_t FRAME_SIZE    = FRAMESIZE_QVGA;   // 320x240, ~10 FPS
static const int      JPEG_QUALITY     = 12;       // 0 best .. 63 worst
static const uint32_t LED_FRAME_MS     = 40;       // effect update rate (25 Hz)
static const int      LED_CLOCK_US     = 10;       // P9813 half-clock (library uses 20)
#ifndef SATELLITE_MIC
#define SATELLITE_MIC 1                            // build with -DSATELLITE_MIC=0 to bisect camera issues
#endif

// ---- XIAO ESP32S3 Sense pins -------------------------------------------------
#define PDM_CLK_PIN   42
#define PDM_DATA_PIN  41
#define LED_CLK_PIN   D2      // Grove yellow (CI)
#define LED_DATA_PIN  D3      // Grove white  (DI)
#define PWDN_GPIO_NUM  -1
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM  10
#define SIOD_GPIO_NUM  40
#define SIOC_GPIO_NUM  39
#define Y9_GPIO_NUM    48
#define Y8_GPIO_NUM    11
#define Y7_GPIO_NUM    12
#define Y6_GPIO_NUM    14
#define Y5_GPIO_NUM    16
#define Y4_GPIO_NUM    18
#define Y3_GPIO_NUM    17
#define Y2_GPIO_NUM    15
#define VSYNC_GPIO_NUM 38
#define HREF_GPIO_NUM  47
#define PCLK_GPIO_NUM  13

// ---- state --------------------------------------------------------------------
static WiFiUDP   udp;
static uint32_t  seq = 0;
static uint32_t  packetsSent = 0;
static bool      cameraOk = false;
static bool      micOk = false;
static uint32_t  lastStatusAt = 0;
static uint8_t   packet[4 + SAMPLES_PER_PKT * 2];
static httpd_handle_t server = NULL;

enum LedEffect { LED_OFF = 0, LED_SOLID, LED_PULSE, LED_BLINK };
static const char *LED_EFFECT_NAMES[] = { "off", "solid", "pulse", "blink" };

struct LedState {
  uint8_t   r, g, b;
  uint8_t   brightness;      // 0..255 scales the colour
  LedEffect effect;
  uint32_t  periodMs;        // pulse / blink cycle
  uint32_t  startedAt;
  uint32_t  sets;            // how often /led was called (status)
};
static LedState led = { 0, 0, 0, 255, LED_OFF, 1500, 0, 0 };
static uint32_t lastLedFrameAt = 0;
static uint8_t  shownR = 255, shownG = 255, shownB = 255;   // force first write

// ---- mood light (P9813 chainable RGB LED, bit-banged) --------------------------
static void ledClock() {
  digitalWrite(LED_CLK_PIN, LOW);
  delayMicroseconds(LED_CLOCK_US);
  digitalWrite(LED_CLK_PIN, HIGH);
  delayMicroseconds(LED_CLOCK_US);
}

static void ledByte(uint8_t value) {
  for (int i = 0; i < 8; i++) {
    digitalWrite(LED_DATA_PIN, (value & 0x80) ? HIGH : LOW);
    ledClock();
    value <<= 1;
  }
}

static void ledWrite(uint8_t r, uint8_t g, uint8_t b) {
  if (r == shownR && g == shownG && b == shownB) return;
  shownR = r; shownG = g; shownB = b;
  for (int i = 0; i < 4; i++) ledByte(0);                  // start frame
  uint8_t prefix = 0xC0;                                   // flag bits + inverted MSBs
  if (!(b & 0x80)) prefix |= 0x20;
  if (!(b & 0x40)) prefix |= 0x10;
  if (!(g & 0x80)) prefix |= 0x08;
  if (!(g & 0x40)) prefix |= 0x04;
  if (!(r & 0x80)) prefix |= 0x02;
  if (!(r & 0x40)) prefix |= 0x01;
  ledByte(prefix);
  ledByte(b); ledByte(g); ledByte(r);
  for (int i = 0; i < 4; i++) ledByte(0);                  // end frame
}

static void startLed() {
  pinMode(LED_CLK_PIN, OUTPUT);
  pinMode(LED_DATA_PIN, OUTPUT);
  digitalWrite(LED_CLK_PIN, HIGH);
  ledWrite(0, 0, 0);
  Serial.println("LED: P9813 on D2/D3");
}

static void setLed(uint8_t r, uint8_t g, uint8_t b, LedEffect effect,
                   uint32_t periodMs, uint8_t brightness) {
  led.r = r; led.g = g; led.b = b;
  led.effect = effect;
  led.periodMs = periodMs < 100 ? 100 : (periodMs > 60000 ? 60000 : periodMs);
  led.brightness = brightness;
  led.startedAt = millis();
  led.sets++;
  lastLedFrameAt = 0;                                      // repaint now
}

static void pumpLed() {
  uint32_t now = millis();
  if (now - lastLedFrameAt < LED_FRAME_MS) return;
  lastLedFrameAt = now;
  float level = 0.0f;
  switch (led.effect) {
    case LED_OFF:   level = 0.0f; break;
    case LED_SOLID: level = 1.0f; break;
    case LED_PULSE: {                                      // cosine breathing, never fully dark
      float phase = (float)((now - led.startedAt) % led.periodMs) / led.periodMs;
      level = 0.08f + 0.92f * (0.5f - 0.5f * cosf(phase * 2.0f * PI));
      break;
    }
    case LED_BLINK: level = ((now - led.startedAt) % led.periodMs) < led.periodMs / 2 ? 1.0f : 0.0f; break;
  }
  level *= led.brightness / 255.0f;
  ledWrite((uint8_t)(led.r * level), (uint8_t)(led.g * level), (uint8_t)(led.b * level));
}

static int ledJson(char *out, size_t size) {
  return snprintf(out, size,
                  "{\"r\":%u,\"g\":%u,\"b\":%u,\"effect\":\"%s\",\"periodMs\":%lu,"
                  "\"brightness\":%u,\"sets\":%lu}",
                  led.r, led.g, led.b, LED_EFFECT_NAMES[led.effect],
                  (unsigned long)led.periodMs, led.brightness, (unsigned long)led.sets);
}

// ---- WiFi ---------------------------------------------------------------------
static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                 // steady audio cadence beats power saving
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("WiFi: joining %s", WIFI_SSID);
  setLed(0, 40, 255, LED_BLINK, 600, 255);   // blue blink = joining WiFi
  uint32_t started = millis();
  uint32_t lastDot = 0;
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    pumpLed();
    delay(20);
    if (millis() - lastDot > 250) { lastDot = millis(); Serial.print('.'); }
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi: %s  rssi %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    setLed(0, 0, 0, LED_OFF, 1500, 255);      // the adapter's mood.py takes over
  } else {
    Serial.println("WiFi: not connected (will keep retrying)");
  }
}

// ---- microphone ----------------------------------------------------------------
// The ESP-IDF driver, not Arduino's I2S.h wrapper: with the wrapper running,
// the camera's frame grabs on this core (2.0.11) never complete (bisected
// 2026-09-03: camera alone fine, wrapper + camera = /snap 500).
static bool startMic() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_PDM);
  cfg.sample_rate = SAMPLE_RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 8;
  cfg.dma_buf_len = SAMPLES_PER_PKT;
  if (i2s_driver_install(I2S_NUM_0, &cfg, 0, NULL) != ESP_OK) {
    Serial.println("Mic: i2s_driver_install failed");
    return false;
  }
  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = I2S_PIN_NO_CHANGE;
  pins.ws_io_num = PDM_CLK_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PDM_DATA_PIN;
  if (i2s_set_pin(I2S_NUM_0, &pins) != ESP_OK) {
    Serial.println("Mic: i2s_set_pin failed");
    return false;
  }
  i2s_zero_dma_buffer(I2S_NUM_0);
  Serial.println("Mic: PDM @16 kHz (idf i2s)");
  return true;
}

static void pumpAudio() {
  if (!micOk || WiFi.status() != WL_CONNECTED) return;
  int16_t *samples = (int16_t *)(packet + 4);
  size_t need = SAMPLES_PER_PKT * 2;
  size_t got = 0;
  while (got < need) {
    size_t n = 0;
    i2s_read(I2S_NUM_0, ((uint8_t *)samples) + got, need - got, &n, pdMS_TO_TICKS(100));
    if (n == 0) { delay(1); continue; }
    got += n;
  }
  for (int i = 0; i < SAMPLES_PER_PKT; i++) {
    int32_t v = ((int32_t)samples[i]) << MIC_GAIN_SHIFT;
    samples[i] = (int16_t)(v > 32767 ? 32767 : (v < -32768 ? -32768 : v));
  }
  packet[0] = seq >> 24; packet[1] = seq >> 16; packet[2] = seq >> 8; packet[3] = seq;
  seq++;
  udp.beginPacket(ADAPTER_HOST, ADAPTER_PORT);
  udp.write(packet, sizeof(packet));
  udp.endPacket();
  packetsSent++;
}

// ---- camera --------------------------------------------------------------------
static bool startCamera() {
  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0;
  c.ledc_timer   = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM;  c.pin_d1 = Y3_GPIO_NUM;  c.pin_d2 = Y4_GPIO_NUM;  c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM;  c.pin_d5 = Y7_GPIO_NUM;  c.pin_d6 = Y8_GPIO_NUM;  c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size   = FRAME_SIZE;
  c.jpeg_quality = JPEG_QUALITY;
  c.fb_count     = 2;
  c.fb_location  = CAMERA_FB_IN_PSRAM;
  c.grab_mode    = CAMERA_GRAB_LATEST;
  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Camera: init failed 0x%x (PSRAM enabled in board options?)\n", err);
    return false;
  }
  sensor_t *s = esp_camera_sensor_get();
  if (s) { s->set_vflip(s, 1); s->set_hmirror(s, 1); }   // mounted upside down on the head
  Serial.println("Camera: OV2640 ready");
  return true;
}


static esp_err_t snapHandler(httpd_req_t *req) {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { httpd_resp_send_500(req); return ESP_FAIL; }
  httpd_resp_set_type(req, "image/jpeg");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  esp_err_t r = httpd_resp_send(req, (const char *)fb->buf, fb->len);
  esp_camera_fb_return(fb);
  return r;
}

static esp_err_t streamHandler(httpd_req_t *req) {
  static const char *BOUNDARY = "\r\n--laika\r\n";
  httpd_resp_set_type(req, "multipart/x-mixed-replace;boundary=laika");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  char part[64];
  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) return ESP_FAIL;
    int len = snprintf(part, sizeof(part), "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    esp_err_t r = httpd_resp_send_chunk(req, BOUNDARY, strlen(BOUNDARY));
    if (r == ESP_OK) r = httpd_resp_send_chunk(req, part, len);
    if (r == ESP_OK) r = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (r != ESP_OK) return r;          // client went away
  }
}

static esp_err_t statusHandler(httpd_req_t *req) {
  char ledBody[128];
  ledJson(ledBody, sizeof(ledBody));
  char body[384];
  snprintf(body, sizeof(body),
           "{\"device\":\"xiao-sense\",\"mic\":%s,\"camera\":%s,\"packets\":%lu,"
           "\"rssi\":%d,\"uptimeS\":%lu,\"adapter\":\"%s:%d\",\"led\":%s}",
           micOk ? "true" : "false", cameraOk ? "true" : "false",
           (unsigned long)packetsSent, WiFi.RSSI(), (unsigned long)(millis() / 1000),
           ADAPTER_HOST, ADAPTER_PORT, ledBody);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, body, strlen(body));
}

static int queryInt(const char *query, const char *key, int fallback, int lo, int hi) {
  char value[16];
  if (httpd_query_key_value(query, key, value, sizeof(value)) != ESP_OK) return fallback;
  int parsed = atoi(value);
  return parsed < lo ? lo : (parsed > hi ? hi : parsed);
}

static esp_err_t ledHandler(httpd_req_t *req) {
  char query[160] = "";
  if (httpd_req_get_url_query_len(req) > 0)
    httpd_req_get_url_query_str(req, query, sizeof(query));
  if (query[0]) {
    LedEffect effect = LED_SOLID;
    char name[12];
    if (httpd_query_key_value(query, "effect", name, sizeof(name)) == ESP_OK) {
      for (int i = 0; i < 4; i++)
        if (strcmp(name, LED_EFFECT_NAMES[i]) == 0) effect = (LedEffect)i;
    } else if (led.effect != LED_OFF) {
      effect = led.effect;
    }
    setLed(queryInt(query, "r", led.r, 0, 255),
           queryInt(query, "g", led.g, 0, 255),
           queryInt(query, "b", led.b, 0, 255),
           effect,
           queryInt(query, "periodMs", led.periodMs, 100, 60000),
           queryInt(query, "brightness", led.brightness, 0, 255));
    pumpLed();
  }
  char body[128];
  int len = ledJson(body, sizeof(body));
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Cache-Control", "no-store");
  return httpd_resp_send(req, body, len);
}

static void startHttp() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.max_open_sockets = 4;
  if (httpd_start(&server, &cfg) != ESP_OK) {
    Serial.println("HTTP: start failed");
    return;
  }
  httpd_uri_t status  = { "/",       HTTP_GET,  statusHandler, NULL };
  httpd_uri_t snap    = { "/snap",   HTTP_GET,  snapHandler,   NULL };
  httpd_uri_t stream  = { "/stream", HTTP_GET,  streamHandler, NULL };
  httpd_uri_t ledGet  = { "/led",    HTTP_GET,  ledHandler,    NULL };
  httpd_uri_t ledPost = { "/led",    HTTP_POST, ledHandler,    NULL };
  httpd_register_uri_handler(server, &status);
  httpd_register_uri_handler(server, &ledGet);
  httpd_register_uri_handler(server, &ledPost);
  if (cameraOk) {
    httpd_register_uri_handler(server, &snap);
    httpd_register_uri_handler(server, &stream);
  }
  Serial.println("HTTP: / /snap /stream /led on port 80");
}

// ---- arduino ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n* hey-laika satellite (xiao-sense) *");
  startLed();
  cameraOk = startCamera();           // before the mic: both use DMA, camera first
  connectWifi();
  micOk = SATELLITE_MIC ? startMic() : false;
  startHttp();
}

void loop() {
  pumpLed();
  if (WiFi.status() != WL_CONNECTED) {
    static uint32_t lastRetry = 0;
    if (millis() - lastRetry > 5000) { lastRetry = millis(); WiFi.reconnect(); }
    delay(20);
    return;
  }
  pumpAudio();
  if (millis() - lastStatusAt > STATUS_PERIOD_MS) {
    lastStatusAt = millis();
    Serial.printf("audio pkts %lu  rssi %d  heap %u  led %s\n",
                  (unsigned long)packetsSent, WiFi.RSSI(), ESP.getFreeHeap(),
                  LED_EFFECT_NAMES[led.effect]);
  }
}
