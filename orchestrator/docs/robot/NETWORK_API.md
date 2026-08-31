# BiBoard Network API Surface

Empirical + source-verified reference of everything the Petoi BiBoard (ESP32) exposes on
the local network.

- **Board under test:** `192.168.0.246` (Bittle X on a BiBoard V1)
- **Live firmware version:** `B10_251121` (from the `?` banner reply)
- **Firmware source snapshot on disk:** `B10_260820`
  (`F:\projects\robot\opencat-esp32\src` — `BOARD "B10"`, `DATE "260820"`)
- **Probe date:** 2026-08-31
- **Tooling:** `F:\projects\robot\dog\.venv\Scripts\python.exe` (Python 3.12.10,
  `websocket-client` 1.9.1)

> Note the version mismatch: the live board runs `B10_251121` (dated 21 Nov 2025) while
> the checked-out firmware source is `B10_260820` (dated 20 Aug 2026). The two are the same
> board family (B10) but different builds. Behaviour below was verified live against
> `B10_251121` and cross-checked against the `B10_260820` source; they agree on the WS
> protocol described here.

---

## 1. Overview — what is exposed, and what is NOT

The board exposes exactly **one** network service:

- **A raw WebSocket server on TCP port 81** (`arduino-WebSocket-Server`, the
  Links2004/arduinoWebSockets library). All robot command-and-control happens over this
  single socket using a small JSON message protocol.

**What does NOT exist (verified empirically):**

- **No HTTP REST API.** There is no HTTP server. Port 80 is closed. An HTTP `GET` to
  port 81 is answered by the WebSocket library with `400 Bad Request` /
  `This is a Websocket server only!` — there are no HTML pages, no `/api/...` routes.
- **No HTTPS / TLS anywhere.** Port 443/8443 closed; the WS endpoint is plain `ws://`,
  not `wss://`.
- **No authentication of any kind.** The WS server accepts any client on the LAN and
  executes its commands. There is no token, password, pairing, or origin check.
- **No OTA / update service listening.** The Arduino ESP32 OTA port 3232 is closed
  (OTA is not compiled in / not advertised on this build).
- **No other services** in the scanned range (1–10000 plus the extra ports below).

### Security consideration

The board has **no authentication and no transport encryption**. Any host on the same
LAN that can reach `192.168.0.246:81` can open a WebSocket and send arbitrary serial
tokens to the robot — including motion, skill, and servo commands that physically move
the dog. The only built-in limit is `MAX_CLIENTS = 2` concurrent WebSocket clients.
Treat network reachability to port 81 as equivalent to full physical control of the
robot, and isolate the board on a trusted network segment accordingly.

---

## 2. TCP port scan results

Scanned from a LAN host on **2026-08-31**. Full range **1–10000** plus extras
**8080, 8081, 8266, 8443, 11434, 3232, 65080**. Threaded connect scan
(`connect_ex`), then every candidate re-confirmed serially with a 2 s timeout and
3 retries to rule out WiFi/ESP32 false negatives.

> Scan note: the ESP32 sits at ~100 ms RTT over WiFi and has a tiny TCP stack. A first
> pass at 0.4 s timeout / 200 concurrent workers produced all-timeouts (false negative);
> results below come from a conservative re-scan (1.0 s timeout, 64 workers, plus a
> serial confirmation pass). Host liveness confirmed by ICMP (TTL 255, ~100 ms).

| Port  | State  | Service / behaviour                                                    |
|-------|--------|-----------------------------------------------------------------------|
| 81    | OPEN   | WebSocket server (`Server: arduino-WebSocket-Server`). Robot C2 API.  |
| 80    | closed | No HTTP server.                                                       |
| 443   | closed | No HTTPS/TLS.                                                         |
| 3232  | closed | No Arduino/ESP32 OTA listener.                                        |
| 8080  | closed | —                                                                    |
| 8081  | closed | —                                                                    |
| 8266  | closed | —                                                                    |
| 8443  | closed | —                                                                    |
| 11434 | closed | No Ollama on the board.                                               |
| 65080 | closed | —                                                                    |
| all other 1–10000 | closed | Nothing else listening.                                  |

**Only open TCP port: 81.**

mDNS/UDP discovery was not exercised in depth; it is not required for control (clients
connect directly to the known IP on port 81). No UDP service is relied upon by the API.

---

## 3. Plain-HTTP probe of the open port

An HTTP `GET / HTTP/1.1` was sent to port 81 to confirm no HTTP surface hides behind it:

```
HTTP/1.1 400 Bad Request
Server: arduino-WebSocket-Server
Content-Type: text/plain
Content-Length: 32
Connection: close
Sec-WebSocket-Version: 13

This is a Websocket server only!
```

This is the arduinoWebSockets library's canned response to a non-Upgrade request. It
confirms there is **no HTTP application** on the board — port 81 speaks only the
WebSocket upgrade handshake.

---

## 4. WebSocket protocol reference

- **Endpoint:** `ws://192.168.0.246:81` (plain WebSocket, subprotocol none, no auth)
- **Encoding:** UTF-8 JSON text frames in both directions.
- **Concurrency limit:** `MAX_CLIENTS = 2`. A 3rd client is sent
  `{"type":"error","error":"Max clients reached"}` and immediately disconnected.
- **Heartbeat idle timeout:** `HEARTBEAT_TIMEOUT = 40000` ms (40 s). A client that sends
  no message for 40 s is sent `{"type":"error","error":"Heartbeat timeout"}` and
  disconnected. (Timeout is relaxed by +15 s while BLE is active.) Health check runs
  every 15 s (`HEALTH_CHECK_INTERVAL`).
- **Task execution timeout:** `WEB_TASK_EXECUTION_TIMEOUT = 45000` ms (45 s) per task.
- **One task at a time:** while a task is running, a new `command` message is rejected —
  the server calls `errorWebTask("Previous web task is still running")` on the active
  task.

### 4.1 On connect

Immediately after the WS upgrade, the server pushes a greeting frame:

```json
{"type":"connected","clientId":"0"}
```

`clientId` is the server-assigned socket number (0 or 1, given MAX_CLIENTS = 2).

### 4.2 Incoming messages (client → board)

**Command** — run an ordered group of serial-console commands:

```json
{
  "type": "command",
  "taskId": "probe1",
  "commands": ["?"],
  "timestamp": 0
}
```

- `taskId` (string): client-chosen id echoed back on every response for this task.
- `commands` (string[]): one or more serial tokens executed **in order**. Each element is
  a full command string whose first character is the OpenCat serial `token` and the rest
  are its arguments (e.g. `"?"`, `"P"`, `"ksit"`, `"m0 30"`).
- `timestamp` (number): client-supplied, not interpreted by the board.

**Heartbeat** — keep the connection alive / measure liveness:

```json
{"type": "heartbeat"}
```

**Malformed input:** any frame that is not valid JSON is answered with
`{"type":"error","error":"Invalid JSON format"}`.

#### Base64 (`b64:`) binary-command prefix

Any element of `commands` may be prefixed with `b64:` to carry **binary/8-bit
arguments** that would not survive as plain text. The board base64-decodes the substring
after `b64:`; the **first decoded byte becomes the `token`** and the remaining decoded
bytes become the (signed 8-bit) argument array. Terminator: if the token is an uppercase
letter `A`–`Z` the decoded command is terminated with `~`, otherwise with `\0`. Use this
for numeric-parameter commands (joint angles, indices) where args are raw signed bytes
rather than ASCII. A `b64:` element that fails to decode is silently skipped.

### 4.3 Outgoing messages (board → client)

**connected** — greeting on connect (see 4.1).

**response (running)** — task acknowledged / a sub-command started. Observed **twice**
per task in practice (one ack when the task is created, one when the first command starts
executing):

```json
{"type":"response","taskId":"probe1","status":"running"}
```

**response (completed)** — all commands in the group finished. `results[i]` is the
captured serial output of `commands[i]`:

```json
{
  "type": "response",
  "taskId": "probe1",
  "status": "completed",
  "results": ["G\r\nBittle X\r\nB10_251121\r\n?\r\n"]
}
```

**response (error)** — task failed, timed out, was superseded, or the client dropped:

```json
{"type":"response","taskId":"<id>","status":"error","error":"Previous web task is still running"}
```

Other `error` strings seen in source: `"Client disconnected"`,
`"Client disconnected due to heartbeat timeout"`, and task-timeout errors.

**heartbeat** — echo/ack of a client heartbeat, carrying the board's `millis()`:

```json
{"type":"heartbeat","timestamp":188153}
```

**error (top-level)** — connection/protocol errors not tied to a task, e.g.
`{"type":"error","error":"Invalid JSON format"}`,
`{"type":"error","error":"Max clients reached"}`,
`{"type":"error","error":"Heartbeat timeout"}`.

### 4.4 Task lifecycle

```
client sends {type:command}
      │
      ├─► server creates WebTask (status "pending")
      │   status → "running"  ──►  {"type":"response",...,"status":"running"}   (ack)
      │
      ├─► executes commands[0..n-1] in order; startWebTask emits a second
      │   {"status":"running"} as the first command begins
      │   each command's serial output is captured into results[i]
      │
      ├─► all commands done
      │       status → "completed"
      │       {"type":"response",...,"status":"completed","results":[...]}
      │
      └─► on failure / timeout (45 s) / disconnect / superseding command
              status → "error"
              {"type":"response",...,"status":"error","error":"..."}
```

Server states (from `WebTask.status`): `pending` → `running` → `completed` | `error`.
Only one task runs at a time; a new command arriving mid-task errors that incoming task.

### 4.5 Push event frames (board → client, unsolicited)

Independent of the task lifecycle, the board broadcasts sensor events to **all** connected
clients when the relevant hardware is present/compiled in:

**Ultrasonic distance** (`sendUltrasonicData`):

```json
{"type":"event_us","distance":42,"timestamp":188000}
```

**Camera / vision detection** (`sendCameraData`, only on `CAMERA` builds): coordinates are
already centre-offset (`x = xCoord - imgRangeX/2`, `y = yCoord - imgRangeY/2`):

```json
{"type":"event_cam","x":-10.0,"y":5.0,"width":40,"height":32,"timestamp":188000}
```

A client must tolerate these arriving interleaved with `response` frames at any time.

---

## 5. Empirical session transcript (live, 2026-08-31)

Single WebSocket client to `ws://192.168.0.246:81`. Only harmless commands were sent
(`?` banner query and a heartbeat). Client closed cleanly afterward.

```
RECV (greeting)  {"type":"connected","clientId":"0"}
SEND             {"type":"command","taskId":"probe1","commands":["?"],"timestamp":0}
RECV             {"type":"response","taskId":"probe1","status":"running"}
RECV             {"type":"response","taskId":"probe1","status":"running"}
RECV             {"type":"response","taskId":"probe1","status":"completed",
                  "results":["G\r\nBittle X\r\nB10_251121\r\n?\r\n"]}
SEND             {"type":"heartbeat"}
RECV (echo)      {"type":"heartbeat","timestamp":188153}
CLOSED cleanly
```

Notes from the live run:

- The greeting `connected` frame arrives before any command is sent.
- Two `running` frames precede `completed` (task-created ack + first-command-start), as
  described in 4.3.
- The `?` command's captured serial output is
  `results[0] = "G\r\nBittle X\r\nB10_251121\r\n?\r\n"` — model **Bittle X**, firmware
  **B10_251121**. This is how to read the live firmware version over the network.
- The heartbeat echo returns the board uptime in ms (`millis()` ≈ 188 s at probe time).

---

## 6. Summary of what does NOT exist

| Capability                       | Present? | Evidence                                                    |
|----------------------------------|----------|-------------------------------------------------------------|
| HTTP REST API                    | No       | Port 80 closed; GET to 81 → `400 This is a Websocket server only!` |
| Any HTML/web UI                  | No       | No HTTP server at all.                                      |
| TLS / HTTPS / `wss://`           | No       | 443/8443 closed; endpoint is plain `ws://`.                 |
| Authentication / authorization   | No       | Server executes commands from any LAN client, no token/pairing. |
| OTA update listener (3232)       | No       | Port 3232 closed.                                           |
| Ollama / other services          | No       | Only port 81 open across 1–10000 + extras.                  |

**Bottom line:** the BiBoard's entire network attack/command surface is one unauthenticated,
unencrypted WebSocket on TCP 81. Anyone who can route to it can drive the robot.
