// hey-laika satellite: XIAO ESP32S3 Sense = Laika's ears and eyes.
//
//  - PDM microphone -> 16 kHz mono int16 PCM -> UDP datagrams to the adapter
//    (4-byte big-endian sequence number + 320 samples = 20 ms per packet).
//    The adapter's ears.py segments utterances and runs whisper.
//  - OV2640 camera -> MJPEG over HTTP on port 80:  /stream (multipart),
//    /snap (one JPEG), / (status JSON). YOLO runs host-side.
//
// Wiring: powered from a spare Grove socket's VCC/GND on the BiBoard (meter
// the rail first, see docs/design/ARRIVAL_DAY_RUNBOOK.md). No data wires to
// the dog: both streams ride the satellite's own WiFi.
//
// Build: arduino-cli compile --fqbn esp32:esp32:XIAO_ESP32S3
//        --board-options "PSRAM=opi" satellite/xiao_sense
// Credentials: copy secrets.h.example to secrets.h.

#include <WiFi.h>
#include <WiFiUdp.h>
#include <I2S.h>
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

// ---- XIAO ESP32S3 Sense pins -------------------------------------------------
#define PDM_CLK_PIN   42
#define PDM_DATA_PIN  41
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

// ---- WiFi ---------------------------------------------------------------------
static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                 // steady audio cadence beats power saving
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("WiFi: joining %s", WIFI_SSID);
  uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi: %s  rssi %d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("WiFi: not connected (will keep retrying)");
  }
}

// ---- microphone ----------------------------------------------------------------
static bool startMic() {
  I2S.setAllPins(-1, PDM_CLK_PIN, PDM_DATA_PIN, -1, -1);
  if (!I2S.begin(PDM_MONO_MODE, SAMPLE_RATE, 16)) {
    Serial.println("Mic: I2S PDM init failed");
    return false;
  }
  Serial.println("Mic: PDM @16 kHz");
  return true;
}

static void pumpAudio() {
  if (!micOk || WiFi.status() != WL_CONNECTED) return;
  int16_t *samples = (int16_t *)(packet + 4);
  size_t need = SAMPLES_PER_PKT * 2;
  size_t got = 0;
  while (got < need) {
    int n = I2S.read(((uint8_t *)samples) + got, need - got);
    if (n <= 0) { delay(1); continue; }
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
  char body[256];
  snprintf(body, sizeof(body),
           "{\"device\":\"xiao-sense\",\"mic\":%s,\"camera\":%s,\"packets\":%lu,"
           "\"rssi\":%d,\"uptimeS\":%lu,\"adapter\":\"%s:%d\"}",
           micOk ? "true" : "false", cameraOk ? "true" : "false",
           (unsigned long)packetsSent, WiFi.RSSI(), (unsigned long)(millis() / 1000),
           ADAPTER_HOST, ADAPTER_PORT);
  httpd_resp_set_type(req, "application/json");
  return httpd_resp_send(req, body, strlen(body));
}

static void startHttp() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = 80;
  cfg.max_open_sockets = 4;
  if (httpd_start(&server, &cfg) != ESP_OK) {
    Serial.println("HTTP: start failed");
    return;
  }
  httpd_uri_t status = { "/",       HTTP_GET, statusHandler, NULL };
  httpd_uri_t snap   = { "/snap",   HTTP_GET, snapHandler,   NULL };
  httpd_uri_t stream = { "/stream", HTTP_GET, streamHandler, NULL };
  httpd_register_uri_handler(server, &status);
  if (cameraOk) {
    httpd_register_uri_handler(server, &snap);
    httpd_register_uri_handler(server, &stream);
  }
  Serial.println("HTTP: / /snap /stream on port 80");
}

// ---- arduino ---------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\n* hey-laika satellite (xiao-sense) *");
  connectWifi();
  micOk = startMic();
  cameraOk = startCamera();
  startHttp();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    static uint32_t lastRetry = 0;
    if (millis() - lastRetry > 5000) { lastRetry = millis(); WiFi.reconnect(); }
    delay(50);
    return;
  }
  pumpAudio();
  if (millis() - lastStatusAt > STATUS_PERIOD_MS) {
    lastStatusAt = millis();
    Serial.printf("audio pkts %lu  rssi %d  heap %u\n",
                  (unsigned long)packetsSent, WiFi.RSSI(), ESP.getFreeHeap());
  }
}
