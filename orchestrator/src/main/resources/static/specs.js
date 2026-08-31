/* Bittle X V2 model specifications — static reference data for the Specs page. */
"use strict";

const BITTLE_SPECS = {
  "Model": {
    "Name": "Petoi Bittle X V2",
    "Introduced": "2023",
    "Dimensions": "15cm (L) × 8cm (W) × 10cm (H)",
    "Weight": "150g",
    "Materials": "Aluminum frame, polymer body",
  },
  "Locomotion": {
    "Max speed": "0.2 m/s",
    "Climbing angle": "15°",
    "Terrain": "Hard, even surfaces",
    "Servos": "8 × FS90R micro servo + arm servo",
    "Servo torque": "1.5 kg/cm",
    "Servo speed": "60°/0.12s",
  },
  "Electrical": {
    "Battery": "7.4V 1000mAh LiPo (JST-XH)",
    "Voltage range": "5.5–8.4V",
    "Runtime (mixed)": "45 minutes",
    "Runtime (idle)": "2+ hours",
    "Charge time": "2 hours (1A charger)",
    "Peak current": "5A",
  },
  "Processor": {
    "Board": "Petoi BiBoard",
    "MCU": "ATmega328P (Arduino-compatible)",
    "Flash / RAM": "32KB / 2KB",
    "Clock": "16MHz",
  },
  "Communications": {
    "Primary": "USB serial (UART) via Micro-USB",
    "Data rate": "115200 baud",
    "Expansion": "UEXT connector (I2C)",
  },
  "Software": {
    "Firmware": "Arduino-compatible C/C++ (OpenCat)",
    "Control": "Serial command protocol + REST via Python adapter",
    "Choreography": "Pre-programmed animation library",
  },
};

const BITTLE_PARTS = {
  "Frame": ["Aluminum legs (4)", "Polymer body", "Servo mounts", "Claw assembly"],
  "Actuators": ["FS90R servos ×8", "Arm servo", "Connectors"],
  "Electrical": ["7.4V LiPo battery", "BiBoard (Arduino)", "USB-UART module", "Power management"],
  "Accessories": ["Micro-USB cable", "SD card slot", "I2C expansion"],
};

const BITTLE_BLUEPRINT_SVG = `
<svg viewBox="0 0 300 400" class="blueprint" role="img" aria-label="Bittle X V2 top view">
  <rect x="1" y="1" width="298" height="398" class="bp-bg"/>
  <text x="150" y="30" text-anchor="middle" class="bp-title">Bittle X V2 — Top View</text>

  <ellipse cx="150" cy="150" rx="80" ry="60" class="bp-body"/>

  <circle cx="100" cy="110" r="12" class="bp-servo"/>
  <circle cx="200" cy="110" r="12" class="bp-servo"/>
  <circle cx="100" cy="190" r="12" class="bp-servo"/>
  <circle cx="200" cy="190" r="12" class="bp-servo"/>

  <line x1="150" y1="110" x2="200" y2="80" class="bp-arm"/>
  <circle cx="200" cy="80" r="8" class="bp-arm-joint"/>
  <text x="212" y="78" class="bp-label">Arm servo</text>

  <rect x="130" y="140" width="40" height="30" class="bp-board"/>
  <text x="150" y="159" text-anchor="middle" class="bp-label">BiBoard</text>

  <rect x="140" y="180" width="20" height="50" class="bp-battery"/>
  <text x="150" y="245" text-anchor="middle" class="bp-label">Battery</text>

  <rect x="145" y="100" width="10" height="15" class="bp-sensor"/>
  <text x="160" y="100" class="bp-label">Sensor mount</text>

  <line x1="100" y1="94" x2="100" y2="55" class="bp-leader"/>
  <text x="100" y="48" text-anchor="middle" class="bp-label">Front left servo</text>
  <line x1="200" y1="124" x2="245" y2="124" class="bp-leader"/>
  <text x="248" y="127" class="bp-label">Front right servo</text>
  <line x1="100" y1="206" x2="100" y2="250" class="bp-leader"/>
  <text x="100" y="262" text-anchor="middle" class="bp-label">Back left servo</text>

  <line x1="20" y1="380" x2="70" y2="380" class="bp-scale"/>
  <text x="45" y="372" text-anchor="middle" class="bp-label">5cm</text>
</svg>`;

function renderSpecsPage(container) {
  const specCards = Object.entries(BITTLE_SPECS).map(([category, rows]) => {
    const items = Object.entries(rows).map(([key, value]) =>
      `<div class="spec-row"><span class="spec-key">${key}</span><span class="spec-value">${value}</span></div>`
    ).join("");
    return `<div class="panel spec-card"><h3>${category}</h3>${items}</div>`;
  }).join("");

  const partCols = Object.entries(BITTLE_PARTS).map(([group, parts]) =>
    `<div class="parts-col"><h4>${group}</h4><ul>${parts.map((p) => `<li>${p}</li>`).join("")}</ul></div>`
  ).join("");

  container.innerHTML = `
    <div class="spec-grid">${specCards}</div>
    <div class="panel-grid">
      <div class="panel"><h3>Hardware blueprint</h3>${BITTLE_BLUEPRINT_SVG}</div>
      <div class="panel"><h3>Parts breakdown</h3><div class="parts-grid">${partCols}</div></div>
    </div>`;
}
