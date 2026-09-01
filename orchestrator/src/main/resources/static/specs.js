/* Per-robot model specifications — revised 2026-09-01 from the validated
 * hardware docs (orchestrator/docs/robot/HARDWARE.md) and the ordered
 * sensor upgrade package. Rendered as a tab on the Robot Detail page. */
"use strict";

// Shared platform facts (both robots are the same model family).
const BASE_SPECS = {
  "Model": {
    "Name": "Petoi Bittle X V2 (voice edition)",
    "Controller": "BiBoard V1.0 - ESP32 (WiFi + BLE + classic BT)",
    "IMU": "ICM42670 (I2C 0x69), drift-compensated yaw",
    "Weight": "~290 g with battery",
  },
  "Electrical": {
    "Battery": "2S LiPo 7.4 V nominal, 1000 mAh (JST-XH)",
    "Full / low / floor": "8.35 V / ~7.0 V warning / 6.8 V cutoff",
    "Servo power": "Long-press the battery's own button",
    "USB": "CH343 USB-UART (USB-C), 115200 8N1 - no auto-reset wiring",
  },
  "Servos": {
    "Physical joints": "9 (head pan +/-90, hips +/-60, knees -90..30)",
    "Firmware indices": "16 (1-7 are placeholders on Bittle X)",
    "Feedback": "Commanded angles only (no position readback)",
    "Interpolation": "~4 ms/degree, completion echo on finish",
  },
  "Connectivity": {
    "Command channel": "WebSocket :81 (JSON tasks, 2-client cap)",
    "Transports": "WiFi (2.4 GHz), BLE UART, classic BT SPP, USB serial",
    "WiFi slots": "Primary (home) + slot 2 (iPhone hotspot) via XW2",
    "Push events": "event_rssi (1 Hz), event_us, exception reports",
  },
  "Firmware": {
    "Build": "hey-laika fork (B10, version-pinned 251121)",
    "Phase A cuts": "No silent drops, reflexes gated, closed-loop turns",
    "Leash/nav tokens": "XWs scan, XWd dead-man, XW2 creds, XWb BLE power",
    "Partition": "min_spiffs (1.9 MB app, ~88% used)",
  },
  "Sound": {
    "Buzzer": "GPIO 2, tone/melody via b token (no DAC on this board)",
    "Voice module": "Mic + fixed/trainable commands on Serial1 (codes only)",
  },
};

// Sensor upgrade package (ordered 2026-09-01). Values are per-robot below.
const PACKAGE_SPECS = {
  "Depth": "Grove Ultrasonic Ranger, 3-350 cm, one-pin mode (UART socket)",
  "Speech": "Grove Speaker Plus, PWM sigma-delta voice (UART socket)",
  "Vision satellite": "XIAO ESP32S3 Sense: OV2640 camera + PDM mic, own WiFi, powered from a Grove socket",
  "Mood light": "Chainable RGB LED on the satellite (D2/D3)",
  "IR receiver": "None (not present on this board)",
};

const ROBOT_SPECS = {
  "bittle-1": {
    subtitle: "Laika - the physical dog",
    overrides: {
      "Identity": {
        "Robot": "Laika (bittle-1)",
        "Hardware": "Real Bittle X V2 at 192.168.0.246 (DHCP reservation advised)",
        "Adapter": "python-bittle-1 (WiFi transport)",
      },
      "Sensor package (ordered)": { ...PACKAGE_SPECS },
    },
  },
  "bittle-2": {
    subtitle: "Mocha - simulated (GUI fixture)",
    overrides: {
      "Identity": {
        "Robot": "Mocha (bittle-2)",
        "Hardware": "Simulated (MOCK_RICH: synthetic RSSI, scans, battery)",
        "Adapter": "python-bittle-2 (mock transport)",
      },
      "Sensor package (assumed)": {
        ...PACKAGE_SPECS,
        "Mood light": "None (package minus the RGB LED)",
        "IR receiver": "None (package minus the IR sensor)",
      },
    },
  },
};

const BITTLE_BLUEPRINT_SVG = `
<svg viewBox="0 0 300 400" class="blueprint" role="img" aria-label="Bittle X V2 top view">
  <rect x="1" y="1" width="298" height="398" class="bp-bg"/>
  <text x="150" y="30" text-anchor="middle" class="bp-title">Bittle X V2 - Top View</text>
  <ellipse cx="150" cy="150" rx="80" ry="60" class="bp-body"/>
  <circle cx="100" cy="110" r="12" class="bp-servo"/>
  <circle cx="200" cy="110" r="12" class="bp-servo"/>
  <circle cx="100" cy="190" r="12" class="bp-servo"/>
  <circle cx="200" cy="190" r="12" class="bp-servo"/>
  <line x1="150" y1="90" x2="150" y2="60" class="bp-line"/>
  <circle cx="150" cy="52" r="10" class="bp-servo"/>
  <text x="150" y="230" text-anchor="middle" class="bp-label">head pan servo + 8 leg servos</text>
  <text x="150" y="250" text-anchor="middle" class="bp-label">BiBoard V1 (ESP32) under the shell</text>
</svg>`;

function renderSpecsPage(container, robotId) {
  const robot = ROBOT_SPECS[robotId] || { subtitle: robotId, overrides: {} };
  const sections = { ...robot.overrides, ...BASE_SPECS };
  // Identity/package first, then base platform sections.
  const html = Object.entries(sections).map(([section, rows]) => `
    <div class="panel">
      <h3>${section}</h3>
      <table class="data-table">
        ${Object.entries(rows).map(([k, v]) =>
          `<tr><td class="muted" style="width:38%">${k}</td><td>${v}</td></tr>`).join("")}
      </table>
    </div>`).join("");
  container.innerHTML =
    `<p class="muted">${robot.subtitle}</p>` +
    `<div class="specs-grid">${html}</div>` + BITTLE_BLUEPRINT_SVG;
}
