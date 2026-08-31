# BITTLE FLEET MANAGEMENT CONSOLE - ENHANCED GUI SPECIFICATION

**Objective:** Transform the temporary UI into a professional fleet management console that reflects the physical reality of Bittle robots, organized by information hierarchy.

**Design Philosophy:** 
- Show what a Bittle X V2 actually IS (specs, parts, diagram)
- Organize information hierarchically (specs → fleet → robot → telemetry)
- Use modern UI patterns (sidebar nav, cards, tabs, live indicators)
- Make it look like real hardware management software

---

## INFORMATION ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────┐
│ Bittle Fleet Management Console (8080)                      │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│  SIDEBAR     │           MAIN CONTENT AREA                  │
│  Navigation  │                                              │
│              │  Dashboard                                   │
│  • Dashboard │  ├─ Fleet overview                           │
│  • Model     │  ├─ Quick stats                              │
│  • Specs     │  └─ Robot grid cards                         │
│  • Robots    │                                              │
│  • Settings  │  Model Specs & Diagram                       │
│              │  ├─ Bittle X V2 specifications              │
│  COLLAPSE    │  ├─ Parts breakdown                         │
│              │  └─ Hardware blueprint (SVG)                │
│              │                                              │
│              │  Robot Detail (per robot selected)          │
│              │  ├─ Live telemetry                          │
│              │  ├─ Personality state                       │
│              │  ├─ Control panel                           │
│              │  └─ Activity log                            │
│              │                                              │
│              │  Settings                                   │
│              │  ├─ Fleet config                            │
│              │  ├─ Service URLs                            │
│              │  └─ Debug info                              │
└──────────────┴──────────────────────────────────────────────┘
```

---

## PAGE STRUCTURE

### 1. DASHBOARD (Default view)

**Layout:**
```
┌─ Fleet Overview ────────────────────────────────────┐
│ Total: 2 | Connected: 2 | Autonomous: 0             │
│ Avg Battery: 87% | Uptime: 2d 14h                   │
└─────────────────────────────────────────────────────┘

┌─ Robot Grid (Responsive) ──────────────────────────┐
│                                                      │
│  ┌──────────────┐  ┌──────────────┐                │
│  │ BITTLE-1     │  │ BITTLE-2     │                │
│  │ ●connected   │  │ ●connected   │                │
│  │ Type: X V2   │  │ Type: X V2   │                │
│  │ Battery: 87% │  │ Battery: 92% │                │
│  │ Mood: Happy  │  │ Mood: Curious│                │
│  │              │  │              │                │
│  │ [Details] [Start]              │  [Details] [Start] │
│  └──────────────┘  └──────────────┘                │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Content:**
- Fleet stat cards (total, connected, autonomous, avg battery, uptime)
- Robot grid (2-3 per row, responsive)
- Each card shows: name, connection status, type, battery, mood
- Click card → navigate to Robot Detail

---

### 2. MODEL SPECS & DIAGRAM

**Layout:**
```
┌─ Bittle X V2 Specifications ───────────────────────┐
│                                                     │
│  PHYSICAL SPECS          ELECTRICAL SPECS          │
│  ├─ Dimensions: 15cm L   ├─ Battery: 7.4V LiPo    │
│  ├─ Weight: 150g         ├─ Max Current: 5A       │
│  ├─ Speed: 0.2 m/s       ├─ Runtime: 45 min       │
│  ├─ Climb: 15°           ├─ Charge Time: 2h       │
│  └─ IP Rating: None      └─ Port: Micro-USB       │
│                                                     │
│  SERVO SPECS             BOARD SPECS              │
│  ├─ Type: FS90R           ├─ MCU: ATmega328P      │
│  ├─ Count: 8 + Arm        ├─ USB: Serial UART     │
│  ├─ Torque: 1.5 kg/cm     ├─ Flash: 32KB          │
│  └─ Speed: 60°/0.12s      └─ RAM: 2KB             │
│                                                     │
└─────────────────────────────────────────────────────┘

┌─ Hardware Blueprint ───────────────────────────────┐
│  (SVG Diagram)                                      │
│   [Bittle top-down view with labeled parts]        │
│   - Servo positions                                │
│   - Battery indicator                              │
│   - Board location                                 │
│   - Arm servo                                      │
│   - Sensor mounting points                         │
└─────────────────────────────────────────────────────┘

┌─ Parts Breakdown ──────────────────────────────────┐
│ Frame                  │ Electrical               │
│ ├─ Aluminum legs (4)  │ ├─ 7.4V LiPo battery    │
│ ├─ Polymer body       │ ├─ BiBoard (Arduino)    │
│ ├─ Servo mounts       │ ├─ USB-UART module      │
│ └─ Claw assembly      │ └─ Power management     │
│                       │                          │
│ Actuators             │ Accessories             │
│ ├─ Servos (FS90R) x8  │ ├─ Micro-USB cable    │
│ ├─ Arm servo          │ ├─ SD card slot        │
│ └─ Connectors         │ └─ I2C expansion       │
└────────────────────────────────────────────────────┘
```

---

### 3. ROBOT DETAIL (Selected Robot)

**Layout:**
```
┌─ Bittle-1: Bittle X V2 ────────────────────────────┐
│ ● connected | Mode: Mock | Last update: 2s ago    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ LIVE TELEMETRY          PERSONALITY STATE         │
│ Battery: 87% ████████░  Energy: 92%  ████████░   │
│ Signal: Strong          Happiness: 78% ███████░   │
│ Autonomous: Off         Boredom: 15%  █░░░░░░░░  │
│ Last Command: walk      Curiosity: 65% ██████░░░ │
│ Commands Sent: 142                                 │
│                         Mood: Happy 😊            │
│ DISPLAY                                           │
│ "Exploring... sniff sniff"                        │
│                                                     │
├─────────────────────────────────────────────────────┤
│                                                     │
│ INTERACTION BUTTONS:  [Pet] [Play] [Talk] [Feed]  │
│                                                     │
│ BEHAVIOR              CHOREOGRAPHY                │
│ [Get Next] "Walking   [Walk Forward]              │
│  because curious"     [Spin Right]                │
│                       [Wave Arm]                  │
│ AUTONOMOUS MODE       [Play Dead]                 │
│ Off [On/Off Toggle]   [Excited Jump]              │
│                                                     │
├─────────────────────────────────────────────────────┤
│ COMMAND INPUT         ACTIVITY LOG                │
│ [Type command...]     14:32 Started autonomous    │
│ kbalance ✓            14:28 Waved arm (animation) │
│                       14:22 Interacted: pet       │
│                       14:15 Mood changed: happy   │
│                       (scrollable, 30 recent)     │
└─────────────────────────────────────────────────────┘
```

---

## VISUAL COMPONENTS

### Robot Card (Grid View)

```html
<div class="robot-card">
  <!-- Connection Status -->
  <div class="status-header">
    <span class="connection-dot connected"></span>
    <span class="robot-name">Bittle-1</span>
    <span class="robot-id">#1</span>
  </div>
  
  <!-- Type Badge -->
  <div class="type-badge">Bittle X V2</div>
  
  <!-- SVG Mini Diagram -->
  <svg class="robot-diagram" viewBox="0 0 100 120">
    <!-- Simple Bittle silhouette -->
    <circle cx="50" cy="40" r="15"/>   <!-- Body -->
    <circle cx="30" cy="60" r="6"/>    <!-- Front left -->
    <circle cx="70" cy="60" r="6"/>    <!-- Front right -->
    <circle cx="30" cy="80" r="6"/>    <!-- Back left -->
    <circle cx="70" cy="80" r="6"/>    <!-- Back right -->
    <path d="M 50 40 L 70 30"/>         <!-- Arm -->
  </svg>
  
  <!-- Quick Stats -->
  <div class="quick-stats">
    <div class="stat">
      <div class="label">Battery</div>
      <div class="value">87%</div>
      <div class="bar"><div class="fill" style="width: 87%"></div></div>
    </div>
    <div class="stat">
      <div class="label">Mood</div>
      <div class="value">Happy 😊</div>
    </div>
  </div>
  
  <!-- Actions -->
  <div class="card-actions">
    <button class="btn-small" onclick="selectRobot('bittle-1')">Details</button>
    <button class="btn-small" onclick="startAutonomous('bittle-1')">Start</button>
  </div>
</div>
```

### Blueprint Diagram (SVG)

```svg
<svg viewBox="0 0 300 400" class="blueprint">
  <!-- Background -->
  <rect width="300" height="400" fill="#f0f0f0" stroke="#333" stroke-width="2"/>
  
  <!-- Title -->
  <text x="150" y="30" text-anchor="middle" font-size="20" font-weight="bold">
    Bittle X V2 - Top View
  </text>
  
  <!-- Body -->
  <ellipse cx="150" cy="150" rx="80" ry="60" fill="#e8e8e8" stroke="#333" stroke-width="2"/>
  
  <!-- Legs -->
  <circle cx="100" cy="110" r="12" fill="#d0d0d0" stroke="#333" stroke-width="2"/>
  <circle cx="200" cy="110" r="12" fill="#d0d0d0" stroke="#333" stroke-width="2"/>
  <circle cx="100" cy="190" r="12" fill="#d0d0d0" stroke="#333" stroke-width="2"/>
  <circle cx="200" cy="190" r="12" fill="#d0d0d0" stroke="#333" stroke-width="2"/>
  
  <!-- Arm (right) -->
  <line x1="150" y1="110" x2="200" y2="80" stroke="#666" stroke-width="4"/>
  <circle cx="200" cy="80" r="8" fill="#999" stroke="#333" stroke-width="1"/>
  
  <!-- Components -->
  <!-- BiBoard -->
  <rect x="130" y="140" width="40" height="30" fill="#ffd700" stroke="#333" stroke-width="1"/>
  <text x="150" y="160" text-anchor="middle" font-size="10">BiBoard</text>
  
  <!-- Battery -->
  <rect x="140" y="180" width="20" height="50" fill="#00aa00" stroke="#333" stroke-width="1"/>
  <text x="150" y="235" text-anchor="middle" font-size="9">Battery</text>
  
  <!-- Sensor Mount -->
  <rect x="150" y="100" width="10" height="15" fill="#ff6600" stroke="#333" stroke-width="1"/>
  <text x="155" y="125" text-anchor="start" font-size="8">Sensor</text>
  
  <!-- Labels with leaders -->
  <line x1="100" y1="70" x2="100" y2="50" stroke="#333" stroke-width="1"/>
  <text x="100" y="45" text-anchor="middle" font-size="9">Front Left Servo</text>
  
  <line x1="200" y1="70" x2="200" y2="50" stroke="#333" stroke-width="1"/>
  <text x="200" y="45" text-anchor="middle" font-size="9">Front Right Servo</text>
  
  <!-- Connector points -->
  <circle cx="150" cy="150" r="2" fill="#ff0000"/>
  <text x="160" y="150" font-size="8" fill="#ff0000">Center</text>
  
  <!-- Scale -->
  <line x1="20" y1="380" x2="70" y2="380" stroke="#333" stroke-width="2"/>
  <text x="45" y="395" text-anchor="middle" font-size="9">5cm</text>
</svg>
```

---

## SIDEBAR NAVIGATION

```html
<nav class="sidebar">
  <div class="sidebar-header">
    <h1>⚙️ Bittle Fleet</h1>
    <span class="version">v1.0</span>
  </div>
  
  <ul class="nav-menu">
    <li class="nav-item active">
      <a href="#dashboard" class="nav-link">
        <span class="icon">📊</span>
        <span class="label">Dashboard</span>
      </a>
    </li>
    
    <li class="nav-item">
      <a href="#specs" class="nav-link">
        <span class="icon">📋</span>
        <span class="label">Model Specs</span>
      </a>
    </li>
    
    <li class="nav-separator">Robots</li>
    
    <li class="nav-item" id="nav-robot-bittle-1">
      <a href="#robot/bittle-1" class="nav-link">
        <span class="icon">🤖</span>
        <span class="label">Bittle-1</span>
        <span class="status-indicator connected">●</span>
      </a>
    </li>
    
    <li class="nav-item" id="nav-robot-bittle-2">
      <a href="#robot/bittle-2" class="nav-link">
        <span class="icon">🤖</span>
        <span class="label">Bittle-2</span>
        <span class="status-indicator disconnected">●</span>
      </a>
    </li>
    
    <li class="nav-separator">System</li>
    
    <li class="nav-item">
      <a href="#settings" class="nav-link">
        <span class="icon">⚙️</span>
        <span class="label">Settings</span>
      </a>
    </li>
    
    <li class="nav-item">
      <a href="#debug" class="nav-link">
        <span class="icon">🐛</span>
        <span class="label">Debug</span>
      </a>
    </li>
  </ul>
  
  <div class="sidebar-footer">
    <button class="btn-collapse" onclick="toggleSidebar()">
      ◀ Collapse
    </button>
  </div>
</nav>
```

---

## SPECSHEET DATA

### Bittle X V2 Specifications

```javascript
const BITTLE_SPECS = {
  model: {
    name: "Petoi Bittle X V2",
    introduced: "2023",
    dimensions: "15cm (L) × 8cm (W) × 10cm (H)",
    weight: "150g",
    materials: "Aluminum frame, Polymer body"
  },
  
  locomotion: {
    maxSpeed: "0.2 m/s",
    climbingAngle: "15°",
    terrain: "Hard, even surfaces",
    servos: {
      type: "FS90R Micro Servo",
      count: 8,
      torque: "1.5 kg/cm",
      speed: "60°/0.12s",
      voltage: "4.8-6V"
    }
  },
  
  electrical: {
    battery: {
      type: "7.4V 1000mAh LiPo",
      voltage: "7.4V nominal (5.5-8.4V range)",
      capacity: "1000mAh",
      runtimeMix: "45 minutes (mixed activity)",
      runtimeIdle: "2+ hours",
      chargeTime: "2 hours (1A charger)",
      connector: "JST-XH"
    },
    power: {
      maxCurrent: "5A peak",
      idleCurrent: "~50mA",
      servoCurrent: "1-2A per servo (active)"
    }
  },
  
  processor: {
    board: "Petoi BiBoard",
    mcu: "ATmega328P (Arduino-compatible)",
    flash: "32KB",
    ram: "2KB",
    clock: "16MHz"
  },
  
  communications: {
    primary: "USB Serial (UART) via Micro-USB",
    dataRate: "115200 baud",
    connectors: "Micro-USB (power + data), UEXT (I2C expansion)"
  },
  
  expansion: {
    i2c: "UEXT connector on BiBoard",
    sensors: "HC-SR04 ultrasonic (on servo mount for radar)",
    display: "I2C OLED via external module",
    storage: "MicroSD card via external module"
  },
  
  software: {
    firmware: "Arduino-compatible C/C++",
    api: "Serial command protocol + REST (via adapter)",
    animationFrames: "Pre-programmed choreography library"
  }
};
```

---

## ENHANCED CSS STRUCTURE

```css
/* Color Scheme */
:root {
  --primary: #2c3e50;
  --accent: #3498db;
  --success: #27ae60;
  --warning: #f39c12;
  --danger: #e74c3c;
  --bg: #ecf0f1;
  --card: #ffffff;
  --text: #2c3e50;
  --text-light: #7f8c8d;
  --border: #bdc3c7;
}

/* Layout */
body {
  display: grid;
  grid-template-columns: 250px 1fr;
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
}

.sidebar {
  grid-column: 1;
  grid-row: 1 / -1;
  background: var(--primary);
  color: white;
  padding: 1rem;
  overflow-y: auto;
  min-height: 100vh;
  position: sticky;
  top: 0;
}

.sidebar.collapsed {
  width: 60px;
}

.main-content {
  grid-column: 2;
  padding: 2rem;
  overflow-y: auto;
}

/* Responsive */
@media (max-width: 768px) {
  body {
    grid-template-columns: 1fr;
  }
  
  .sidebar {
    position: fixed;
    left: 0;
    top: 0;
    height: 100vh;
    transform: translateX(-100%);
    transition: transform 0.3s ease;
    z-index: 1000;
  }
  
  .sidebar.open {
    transform: translateX(0);
  }
  
  .main-content {
    grid-column: 1;
  }
}

/* Robot Cards */
.robot-card {
  background: var(--card);
  border-radius: 8px;
  border: 1px solid var(--border);
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
  transition: all 0.3s ease;
  cursor: pointer;
}

.robot-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  transform: translateY(-2px);
}

.robot-card.selected {
  border-color: var(--accent);
  background: #f0f7ff;
}

.status-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
  font-weight: 600;
}

.connection-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
}

.connection-dot.connected {
  background: var(--success);
  box-shadow: 0 0 8px var(--success);
}

.connection-dot.disconnected {
  background: var(--danger);
}

.robot-diagram {
  width: 100%;
  height: 100px;
  margin: 1rem 0;
  background: #f9f9f9;
  border-radius: 4px;
}

/* Personality Bars */
.personality-bar {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin: 1rem 0;
}

.personality-trait {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.personality-trait .label {
  width: 100px;
  font-size: 0.9rem;
  font-weight: 500;
}

.personality-trait .bar-container {
  flex: 1;
  height: 20px;
  background: #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.personality-trait .bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #3498db, #2ecc71);
  transition: width 0.3s ease;
}

.personality-trait .value {
  width: 50px;
  text-align: right;
  font-weight: 600;
}

/* Activity Log */
.activity-log {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1rem;
}

.activity-entry {
  padding: 0.5rem 0;
  border-bottom: 1px solid #f0f0f0;
  font-size: 0.9rem;
}

.activity-entry:last-child {
  border-bottom: none;
}

.activity-time {
  color: var(--text-light);
  font-size: 0.85rem;
  margin-right: 0.5rem;
}

/* Buttons */
.btn-small {
  padding: 0.4rem 0.8rem;
  font-size: 0.9rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--card);
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-small:hover {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}

/* Tabs */
.tabs {
  display: flex;
  border-bottom: 2px solid var(--border);
  margin-bottom: 1rem;
}

.tab {
  padding: 0.75rem 1.5rem;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  margin-bottom: -2px;
  transition: all 0.3s ease;
}

.tab:hover {
  background: rgba(52, 152, 219, 0.1);
}

.tab.active {
  border-bottom-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}
```

---

## IMPLEMENTATION ROADMAP

### Phase 1: Information Architecture
- [ ] Create sidebar navigation component
- [ ] Implement tab/route system (Dashboard, Specs, Robot Detail, Settings)
- [ ] Add navigation state management

### Phase 2: Specs & Diagram Page
- [ ] Add specs data structure (BITTLE_SPECS)
- [ ] Create specs display page with columns
- [ ] Build SVG blueprint diagram
- [ ] Add parts breakdown section

### Phase 3: Enhanced Robot Cards
- [ ] Redesign robot card component
- [ ] Add SVG mini-diagram to cards
- [ ] Improve battery/mood display
- [ ] Add selection state styling

### Phase 4: Robot Detail Panel
- [ ] Reorganize data display (telemetry, personality, control)
- [ ] Improve personality bar visualization
- [ ] Add interaction buttons with better layout
- [ ] Enhance activity log with better styling

### Phase 5: Responsive & Polish
- [ ] Mobile-friendly sidebar (collapsible)
- [ ] Responsive grid for robot cards
- [ ] Touch-friendly buttons
- [ ] Performance optimization

### Phase 6: Advanced Features (Future)
- [ ] Real-time WebSocket updates (replace polling)
- [ ] Robot model customization
- [ ] Drag-and-drop choreography builder
- [ ] Fleet statistics dashboard
- [ ] Robot health monitoring/alerts

---

## KEY IMPROVEMENTS

✅ **Visual Hierarchy** - Sidebar nav, clear sections, proper spacing
✅ **Physical Context** - See what Bittle actually is (specs, diagram)
✅ **Better Cards** - Mini diagrams, better status display, selection
✅ **Information Organization** - Group related data logically
✅ **Professional Look** - Modern UI patterns, proper colors, typography
✅ **Responsive Design** - Works on desktop, tablet, mobile
✅ **Extensible** - Easy to add new pages/sections

---

## NEXT STEPS

1. **Agree on structure** - Do you like the sidebar layout and page organization?
2. **Create component files** - Separate HTML/CSS/JS for each section
3. **Build specs data** - Finalize Bittle specs (I can refine)
4. **SVG diagrams** - Create blueprint and mini-diagrams
5. **Integration** - Connect to existing REST API

Ready to code this out?
