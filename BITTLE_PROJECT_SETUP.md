# BITTLE AI COMPANION - COMPLETE PROJECT BRIEF

**Status:** Phase 0 - Foundation Setup
**Last Updated:** [Today's Date]
**Project Type:** AI-Powered Autonomous Robot Dog with Local LLM Orchestration

---

## EXECUTIVE SUMMARY

Building a complete management system for an AI robot dog (Petoi Bittle X V2) that:
- Uses Claude for autonomous decision-making via multi-turn conversations
- Persists all personality state, behavior logs, and interactions to database
- Supports multiple robot types through adapter pattern
- Runs locally with SQLite now, scales to PostgreSQL + AWS later
- Streams content (images/text/video) to phone/projector on robot

**Timeline:** 1 month to full system (4 weeks × 8-12 hours)
**Hardware Cost:** ~$400 (Bittle kit already ordered)
**Tech Stack:** Python + Flask + SQLAlchemy + Anthropic SDK + Docker

---

## COMPLETE TECH STACK

### Backend
- **Language:** Python 3.11+
- **Framework:** Flask 3.0+ (WSGI server: Gunicorn)
- **Database ORM:** SQLAlchemy 2.0+
- **Migrations:** Alembic 1.12+
- **API Style:** REST (JSON)

### Database
- **Development:** SQLite 3.x
- **Production:** PostgreSQL 15+
- **Abstraction:** SQLAlchemy (database-agnostic)

### AI/LLM
- **SDK:** Anthropic Python SDK 0.7+
- **Model:** Claude 3.5 Sonnet (latest)
- **Integration:** Multi-turn conversation with persistent history

### Hardware Communication
- **Serial:** PySerial 3.5 (USB ↔ Bittle)
- **WiFi:** Requests library (HTTP to WiFi module)
- **Pattern:** Adapter pattern for multi-robot support

### Frontend
- **Display:** HTML5 + CSS3 + Vanilla JavaScript (ES6)
- **Templating:** Jinja2 (built into Flask)
- **Pages:** Dashboard (control) + Display (phone/projector)

### DevOps
- **Containerization:** Docker + Docker Compose
- **Cloud:** AWS-ready (ECS, RDS, S3, CloudFormation)
- **CI/CD:** GitHub Actions (template provided)
- **Version Control:** Git + GitHub

### Testing
- **Framework:** Pytest 7.4+
- **Coverage:** Pytest-cov 4.1+

---

## PROJECT ARCHITECTURE

```
┌──────────────────────────────────────┐
│  Flask Server (app.py)               │
│  ├─ REST endpoints                   │
│  └─ WebSocket-ready                  │
└────────────┬─────────────────────────┘
             │
    ┌────────┼────────┬────────┐
    ▼        ▼        ▼        ▼
┌────────┐ ┌──────┐ ┌──────┐ ┌──────┐
│Claude  │ │SQLAlc│ │Adapt-│ │Chor-│
│SDK     │ │hemy  │ │ers   │ │eo   │
│API     │ │ORM   │ │      │ │Lib  │
└────────┘ └──────┘ └──────┘ └──────┘
           │
    ┌──────▼──────┐
    │  SQLite DB  │
    └─────────────┘
           │
    ┌──────▼─────────────┐
    │  BittleAdapter     │
    │  ├─ Serial (USB)   │
    │  ├─ WiFi           │
    │  └─ Mock           │
    └────────────────────┘
           │
    ┌──────▼──────────┐
    │  Bittle Robot   │
    │  ├─ Servos      │
    │  ├─ LEDs        │
    │  └─ Sensors     │
    └─────────────────┘
```

---

## COMPLETE FILE STRUCTURE

```
bittle-ai-companion/
│
├── README.md                      # Project documentation
├── CONTEXT.md                     # Active development context
├── PROJECT_STATUS.md              # Phase tracking
├── ARCHITECTURE.md                # Design decisions
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Container image
├── docker-compose.yml             # Local dev environment
├── .env.example                   # Environment template
├── .gitignore                     # Git ignore rules
│
├── app/
│   ├── __init__.py               # Package init
│   ├── app.py                    # Main Flask application
│   ├── config.py                 # Configuration management
│   ├── models.py                 # SQLAlchemy models
│   ├── bittle_controller.py      # Hardware abstraction
│   ├── personality_engine.py     # Claude integration
│   ├── choreography.py           # Animation library
│   │
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base_adapter.py       # Abstract adapter
│   │   └── bittle_adapter.py     # Bittle implementation
│   │
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── robot_repository.py
│   │   ├── personality_repository.py
│   │   ├── behavior_repository.py
│   │   └── conversation_repository.py
│   │
│   └── services/
│       ├── __init__.py
│       └── robot_service.py
│
├── templates/
│   ├── base.html                 # Base template
│   ├── dashboard.html            # Control panel
│   └── display.html              # Phone/projector display
│
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── display.js
│
├── tests/
│   ├── __init__.py
│   ├── test_personality.py
│   ├── test_choreography.py
│   ├── test_bittle_controller.py
│   └── test_robot_service.py
│
└── scripts/
    ├── setup.sh                  # Initial setup
    └── ask.sh                    # CLI context helper
```

---

## PHASE 0: FOUNDATION SETUP (Days 1-3)

### Goals
1. ✅ Project initialized with all core files
2. ✅ Docker Compose local development working
3. ✅ Web dashboard accessible at http://localhost:5000
4. ✅ Claude making autonomous decisions (simulated, no hardware)
5. ✅ Database schema ready
6. ✅ GitHub repo initialized

### Success Criteria
- Run `docker-compose up`
- Open http://localhost:5000
- See mock Bittle making Claude-powered decisions
- Click animations in dashboard
- No hardware needed

### Files to Generate

#### 1. `requirements.txt`
```
Flask==3.0.0
Flask-CORS==4.0.0
Gunicorn==21.2.0
python-dotenv==1.0.0
requests==2.31.0
anthropic==0.7.0
Pillow==10.0.0
pyserial==3.5
SQLAlchemy==2.0.0
alembic==1.12.0
pytest==7.4.0
pytest-cov==4.1.0
```

#### 2. `app/config.py`
Environment-based configuration for development/production/AWS

#### 3. `app/models.py`
SQLAlchemy models for:
- Robot (generic robot definition)
- Personality (per-robot state)
- Interaction (user feedback logs)
- BehaviorLog (everything Claude decided)
- ConversationMessage (context history)
- ChoreographyLibrary (animations per robot type)
- SystemConfiguration (global settings)

#### 4. `app/bittle_controller.py`
Hardware abstraction layer with three implementations:
- MockBittleController (simulation, no hardware)
- SerialBittleController (USB communication)
- WiFiBittleController (WiFi module communication)

Factory function: `create_bittle_controller()`

#### 5. `app/personality_engine.py`
Claude integration with:
- PersonalityEngine class
- Multi-turn conversation history
- Personality state tracking (energy, boredom, happiness, etc)
- `get_next_behavior()` method (asks Claude for decision)
- Database persistence

#### 6. `app/choreography.py`
Animation library with:
- AnimationFrame dataclass
- ChoreographyLibrary class (pre-programmed sequences)
- Animations: walk_forward, spin_right, wave_arm, play_dead, stretch, excited_jump, curious_sniff
- Build command sequences for robot

#### 7. `app/app.py`
Main Flask application with endpoints:

**Health & Status:**
- `GET /api/health` → system status
- `GET /api/personality` → personality state
- `GET /bittle/status` → hardware status

**Behavior:**
- `GET /api/personality/behavior` → get Claude's decision
- `POST /api/personality/interact/<type>` → log interaction
- `GET /api/choreography/list` → list animations
- `POST /api/choreography/execute/<animation>` → execute animation

**Autonomous Mode:**
- `POST /api/autonomous/start` → start behavior loop
- `POST /api/autonomous/stop` → stop behavior loop
- `GET /api/autonomous/status` → get loop status

**Web UI:**
- `GET /` → dashboard (control panel)
- `GET /display` → phone/projector display

#### 8. `docker-compose.yml`
Local development environment:
- Flask service (port 5000)
- Volume mounts for code + USB serial
- Health checks
- Logging configuration
- Optional PostgreSQL service (commented out for Phase 0)

#### 9. `Dockerfile`
Production-ready image:
- Python 3.11 slim base
- System dependencies
- Python dependencies
- Gunicorn WSGI server
- Health check

#### 10. `.env.example`
```
ENVIRONMENT=development
DEBUG=True
MOCK_MODE=True
ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE
BITTLE_COMMUNICATION_METHOD=mock
DATABASE_TYPE=sqlite
SQLITE_DB_PATH=./bittle.db
PERSISTENCE_ENABLED=True
SAVE_CONVERSATION_HISTORY=True
SAVE_BEHAVIOR_LOG=True
```

#### 11. `templates/dashboard.html`
Control panel with sections:
- Status (Bittle connection, mode, autonomous status)
- Personality (energy bar, mood, boredom, happiness)
- Autonomous mode controls
- Quick animation buttons
- User interaction buttons (pet, play, talk, feed)
- Activity log (real-time log of actions)
- Live personality stats

#### 12. `templates/display.html`
Phone/projector display:
- Full-screen display area
- Receives content updates via `/current` endpoint
- Handles text, images, videos
- Auto-refresh every 5 seconds

#### 13. `.gitignore`
Standard Python + environment ignores

#### 14. `README.md`
Complete project documentation with:
- Overview
- Quick start
- Architecture
- API documentation
- Development workflow
- Deployment instructions

---

## EXECUTION STEPS

### Step 1: Initialize Repository
```bash
git init bittle-ai-companion
cd bittle-ai-companion

# Create context files
cat > CONTEXT.md << 'EOF'
# BITTLE AI COMPANION - ACTIVE CONTEXT

Phase: 0
Status: Starting Foundation Setup
Updated: [Now]

Current Task: Generate Phase 0 files

Next Session:
- All files generated
- Docker-compose running
- Dashboard accessible
EOF

git add CONTEXT.md
git commit -m "Initialize project with context"
```

### Step 2: Generate Files (Use Claude CLI or Paste)
For each file listed above, either:

**Option A: Claude CLI**
```bash
claude create requirements.txt "
Create Python requirements file with:
- Flask 3.0.0
- SQLAlchemy 2.0.0
- Anthropic SDK
- PySerial
- Pytest
[... all packages listed in requirements.txt section above]
"
```

**Option B: Copy-Paste into IntelliJ**
Create each file manually in IntelliJ, paste content

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run Docker (or Flask directly)
```bash
# Option 1: Docker
docker-compose up

# Option 2: Direct Flask
python -m app.app
```

### Step 5: Verify
Open http://localhost:5000 in browser. You should see:
- Dashboard with status
- Mock Bittle (simulated, no hardware)
- Personality stats
- Animation buttons

### Step 6: Test Autonomous Mode
1. Click "Start" in Autonomous Mode section
2. Watch dashboard log actions
3. See Claude decisions in real-time
4. Observe personality state changes

### Step 7: Commit Phase 0
```bash
git add .
git commit -m "Complete Phase 0: Foundation setup

- Flask server running
- SQLite database initialized
- Mock Bittle adapter working
- Claude integration active
- Web dashboard operational
- All Phase 0 deliverables complete"
```

---

## IMPORTANT CONFIGURATION

### Environment Variables
**MUST SET in .env:**
```
ANTHROPIC_API_KEY=sk-ant-[your-actual-key]
ENVIRONMENT=development
MOCK_MODE=True (change to False when hardware arrives)
```

### Database
Phase 0 uses SQLite. No setup needed—created automatically.

### Claude Integration
Requires valid Anthropic API key. Get from: https://console.anthropic.com/

---

## TESTING PHASE 0

### Manual Testing
1. Open http://localhost:5000
2. Click animation buttons → See logs
3. Interact buttons → Watch personality change
4. Start autonomous → See Claude decisions loop

### Automated Testing
```bash
pytest tests/ -v
```

### Health Check
```bash
curl http://localhost:5000/api/health
```

Should return:
```json
{
  "status": "healthy",
  "bittle": {"connected": true, "mode": "mock"},
  "personality": {"energy": 100, "mood": "neutral"},
  "autonomous": false,
  "environment": "development",
  "mock_mode": true
}
```

---

## NEXT PHASES (After Phase 0 Complete)

### Phase 1: Bittle Hardware Integration (Days 4-7)
- Assemble Bittle X V2
- Connect USB
- Change `BITTLE_COMMUNICATION_METHOD=serial`
- Test real hardware movement

### Phase 2: Display System (Days 8-10)
- Mount phone on Bittle
- Stream content via Flask
- Synchronized movement + display

### Phase 3: LED & Flashlight (Days 11-12)
- Wire LED to GPIO
- Personality-based patterns
- Mood visualization

### Phase 4: WiFi Module (Days 13-14)
- Install ESP8266 module
- Change to `BITTLE_COMMUNICATION_METHOD=wifi`
- Enable autonomous roaming

### Phase 5: Sensor Integration (Days 15-21)
- Add sensor pack
- Ultrasonic + servo radar
- Claude uses sensor input

### Phase 6: Polish & Refinement (Days 22-28)
- Extended choreography library
- Multiple personality profiles
- Advanced interactions
- Documentation

### Phase 7: Cloud Deployment (Week 5+, Optional)
- PostgreSQL on AWS RDS
- Deploy to ECS
- GitHub Actions CI/CD
- Multi-robot support

---

## PHASE TIMELINE TABLE

| PHASE | TIMELINE | HARDWARE NEEDED | DELIVERABLES | TIME |
|-------|----------|-----------------|---------------|------|
| 0 | Days 1-3 | None (mock mode) | Code + Local system | 8h |
| 1 | Days 4-7 | Bittle + USB | Real hardware working | 6h |
| 2 | Days 8-10 | Phone/Projector | Display streaming | 4h |
| 3 | Days 11-12 | LED + resistor | Visual feedback | 3h |
| 4 | Days 13-14 | WiFi module | Wireless control | 3h |
| 5 | Days 15-21 | Sensor pack | Environmental awareness | 8h |
| 6 | Days 22-28 | None | Polish & refinement | 10h |
| 7 | Week 5+ | None | Cloud deployment | 10h |
| **TOTAL** | **1 month** | **~$400** | **Full AI robot system** | **52h** |

---

## KEY DECISIONS

- **Python over Java:** Robotics + AI standard, no overkill
- **Flask over FastAPI:** Lightweight, perfect for single-robot (async later if needed)
- **SQLite first:** Zero setup, migrate to PostgreSQL when scaling
- **Adapter pattern:** Support multiple robot types from day one
- **Personality persistence:** Every decision logged for analysis
- **Mock mode first:** Test without hardware immediately
- **Claude for everything:** All decision-making via LLM

---

## DEVELOPER WORKFLOW

### Daily Workflow
1. Open this brief
2. Check current phase & tasks
3. Use Claude CLI with context: `./ask.sh "What's next?"`
4. Edit in IntelliJ
5. Test locally with `docker-compose up` or `python -m app.app`
6. Commit to git
7. Update CONTEXT.md

### Using Claude CLI
```bash
# Generate file with full context
claude create app/new_module.py "
$(cat CONTEXT.md)

Create [description]"

# Ask question with context
./ask.sh "Getting error: [error]. Fix?"

# Review code with context
claude review app/app.py "
$(cat ARCHITECTURE.md)

Review this code."
```

### Using This Chat (Web UI)
- Paste code snippets
- Ask architecture questions
- Brainstorm features
- Debugging help
- Context updates

---

## SUPPORT & DEBUGGING

### Common Issues

**ImportError: No module named 'anthropic'**
```bash
pip install -r requirements.txt
```

**Port 5000 already in use**
```bash
# Change in config.py or:
lsof -i :5000
kill -9 [PID]
```

**SQLite database locked**
```bash
# Restart flask/docker
docker-compose restart
```

**Claude API error**
- Verify ANTHROPIC_API_KEY in .env
- Check key has valid credits
- Verify network connectivity

### Getting Help
1. Paste error in chat with CONTEXT.md
2. I'll diagnose with full context
3. Provide fix + explanation

---

## SUCCESS CRITERIA: PHASE 0 COMPLETE

- [ ] Project cloned/initialized
- [ ] All files generated
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Docker Compose running OR Flask running directly
- [ ] Dashboard accessible at http://localhost:5000
- [ ] Mock Bittle making Claude decisions
- [ ] Database initialized (bittle.db created)
- [ ] Autonomous mode toggles work
- [ ] Animation buttons trigger logs
- [ ] Personality state changes visible
- [ ] `/api/health` returns 200 status
- [ ] Code committed to git
- [ ] CONTEXT.md updated with completion status

**Estimated Time:** 6-8 hours spread across 3 days

---

## READY TO START?

When you have this file:

1. **For Claude CLI:** Pass it directly
   ```bash
   claude < BITTLE_PROJECT_SETUP.md
   ```

2. **For This Chat:** Reference it
   > "Using the setup file. Ready for Phase 0. Should I generate files with CLI or paste into IntelliJ?"

3. **For IntelliJ:** Keep it as reference
   - File → Open → Keep BITTLE_PROJECT_SETUP.md in editor
   - Follow structure while creating files

---

## QUESTIONS ANSWERED IN ADVANCE

**Q: Do I need Bittle hardware for Phase 0?**
A: No. Mock adapter simulates everything.

**Q: Do I need to understand all the code?**
A: No. Start with Phase 0, understand as you go.

**Q: Can I use this from scratch with no Python experience?**
A: Yes. This is designed for rapid iteration.

**Q: What if I hit an error?**
A: Paste the error + CONTEXT.md in chat. I'll debug.

**Q: Can I deploy to AWS now?**
A: Not until Phase 7. Local first.

**Q: Do I need PostgreSQL?**
A: No. SQLite works great for development.

**Q: Can I add more features?**
A: Yes, after Phase 0. Build on the foundation.

---

## NEXT STEPS

1. **Download this file** (BITTLE_PROJECT_SETUP.md)
2. **Pass to Claude CLI** or reference in chat
3. **Initialize git repo** (Step 1 above)
4. **Generate Phase 0 files** (Step 2 above)
5. **Install dependencies** (Step 3 above)
6. **Run locally** (Step 4 above)
7. **Verify success** (Step 5 above)

**Let's build 🚀**
