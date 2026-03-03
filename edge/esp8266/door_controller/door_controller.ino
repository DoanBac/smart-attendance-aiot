/**
 * ============================================================
 *  AIoT Smart Attendance — Door Controller (ESP8266 / NodeMCU)
 *  Architecture: Backend → HTTP → ESP8266 (web server mode)
 * ============================================================
 *
 *  Wiring (NodeMCU pin labels):
 *    D1  (GPIO5)  → RELAY   — one channel relay module (IN pin)
 *    D2  (GPIO4)  → LED_GREEN
 *    D3  (GPIO0)  → LED_RED
 *    D4  (GPIO2)  → BUZZER  (passive buzzer)
 *    D5  (GPIO14) → BUTTON  (exit button, pulled HIGH, shorts to GND)
 *
 *  Relay wiring (module has built-in optocoupler — two circuits ISOLATED):
 *
 *  Control side (5V):              Load side (12V) — ISOLATED from control side
 *    NodeMCU VIN (5V) → Relay VCC    12V(+) ──────────────── Electromagnet (+)
 *    NodeMCU GND      → Relay GND    Electromagnet (-) ────── Relay NO
 *    NodeMCU D1       → Relay IN     Relay COM ─────────────── 12V(-)
 *
 *  Active-LOW relay module, NO contact:
 *    IN LOW  → relay energised → NO closes → magnet ON  → door LOCKED  (idle)
 *    IN HIGH → relay off       → NO opens  → magnet OFF → door UNLOCKED
 *
 *  ⚠ Do NOT connect 12V GND to ESP8266 GND.
 *
 *  HTTP endpoints (backend calls these):
 *    POST /door/scan   → face scanning started (red LED blinks)
 *    POST /door/open   → access granted (green LED + unlock 3s + beep)
 *    POST /door/deny   → access denied  (red LED blinks 2s + 3 beeps)
 *
 *  Exit button → ESP8266 calls backend:
 *    POST http://BACKEND_HOST/api/devices/exit   (X-Device-Token header)
 *    Backend logs the event and broadcasts WS to dashboard.
 *
 *  Setup in Admin panel (Devices page):
 *    esp8266_url = http://<ESP8266_IP>   ← backend uses this to call endpoints above
 *
 *  Libraries required (Arduino Library Manager):
 *    - ESP8266WiFi       (bundled with esp8266 core)
 *    - ESP8266WebServer  (bundled with esp8266 core)
 *    - ESP8266HTTPClient (bundled with esp8266 core)
 * ============================================================
 */

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <WiFiClient.h>

// ─── User configuration ──────────────────────────────────────────────────────
const char* WIFI_SSID     = "Doan Bac";
const char* WIFI_PASSWORD = "999999999";

// Backend — for exit button HTTP call only
const char* BACKEND_HOST  = "192.168.123.134";
const int   BACKEND_PORT  = 8000;
const char* DEVICE_TOKEN  = "1e1bc45444c2439ab40255bd8243148a";

// ─── GPIO ────────────────────────────────────────────────────────────────────
#define RELAY      5   // D1
#define LED_GREEN  4   // D2
#define LED_RED    0   // D3
#define BUZZER     2   // D4
#define BUTTON    14   // D5

// Relay logic — active-LOW module, NO contact
#define LOCK_LEVEL   LOW    // energised → NO closes → magnet ON  → LOCKED
#define UNLOCK_LEVEL HIGH   // off       → NO opens  → magnet OFF → UNLOCKED

// ─── Durations ───────────────────────────────────────────────────────────────
const unsigned long UNLOCK_MS       = 3000;   // door open duration
const unsigned long DENIED_BLINK_MS = 2000;   // denied animation duration
const unsigned long SCAN_TIMEOUT_MS = 8000;   // max wait for open/deny after scan
const unsigned long BEEP_MS         = 120;
const unsigned long BTN_DEBOUNCE_MS = 50;

// ─── State machine ───────────────────────────────────────────────────────────
enum DoorState { IDLE, SCANNING, GRANTED, DENIED, EXIT_OPEN };
DoorState     state       = IDLE;
unsigned long stateTimer  = 0;

// ─── Globals ─────────────────────────────────────────────────────────────────
ESP8266WebServer server(80);

bool          buttonWasLow    = false;
unsigned long lastBtnTime     = 0;
bool          pendingExitHttp = false;

unsigned long lastBlinkMs = 0;
bool          blinkState  = false;

// ─── Door helpers ─────────────────────────────────────────────────────────────
void lockDoor()   { digitalWrite(RELAY, LOCK_LEVEL);   }
void unlockDoor() { digitalWrite(RELAY, UNLOCK_LEVEL); }
void greenOn()    { digitalWrite(LED_GREEN, HIGH); }
void greenOff()   { digitalWrite(LED_GREEN, LOW);  }
void redOn()      { digitalWrite(LED_RED,   HIGH); }
void redOff()     { digitalWrite(LED_RED,   LOW);  }
void allLedOff()  { greenOff(); redOff(); }

void beep(int count = 1, int ms = BEEP_MS, int pauseMs = 80) {
  for (int i = 0; i < count; i++) {
    tone(BUZZER, 2000, ms);
    delay(ms + pauseMs);
  }
  noTone(BUZZER);
}

// ─── State transitions ────────────────────────────────────────────────────────
void enterIdle() {
  lockDoor();
  allLedOff();
  redOn();
  noTone(BUZZER);
  state = IDLE;
  stateTimer = millis();
  Serial.println("[DOOR] IDLE — locked");
}

void enterScanning() {
  lockDoor();          // keep locked while scanning
  allLedOff();
  lastBlinkMs = millis();
  blinkState  = false;
  state = SCANNING;
  stateTimer = millis();
  Serial.println("[DOOR] SCANNING — waiting for result");
}

void enterGranted() {
  unlockDoor();
  allLedOff();
  greenOn();
  beep(1);
  state = GRANTED;
  stateTimer = millis();
  Serial.println("[DOOR] GRANTED — unlocked 3s");
}

void enterDenied() {
  lockDoor();
  allLedOff();
  beep(3, 80, 60);
  lastBlinkMs = millis();
  blinkState  = false;
  state = DENIED;
  stateTimer = millis();
  Serial.println("[DOOR] DENIED");
}

void enterExit() {
  unlockDoor();
  allLedOff();
  greenOn();
  beep(1, 60);
  state = EXIT_OPEN;
  stateTimer = millis();
  Serial.println("[DOOR] EXIT — unlocked 3s");
}

// ─── HTTP server handlers (called by kiosk browser directly) ────────────────
void addCors() {
  // Allow browser (kiosk) on same LAN to call ESP8266 directly
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");
}

void handleOptions() {
  addCors();
  server.send(204);
}

void handleDoorScan() {
  addCors();
  server.send(200, "application/json", "{\"ok\":true}");
  if (state == IDLE) enterScanning();
}

void handleDoorOpen() {
  addCors();
  server.send(200, "application/json", "{\"ok\":true}");
  enterGranted();
}

void handleDoorDeny() {
  addCors();
  server.send(200, "application/json", "{\"ok\":true}");
  enterDenied();
}

void handleNotFound() {
  server.send(404, "text/plain", "Not found");
}

// ─── Exit button → backend HTTP (non-blocking) ────────────────────────────────
void sendExitRequest() {
  if (WiFi.status() != WL_CONNECTED) return;
  WiFiClient client;
  HTTPClient http;
  http.setTimeout(1500);
  String url = String("http://") + BACKEND_HOST + ":" + BACKEND_PORT + "/api/devices/exit";
  if (http.begin(client, url)) {
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Token", DEVICE_TOKEN);
    int code = http.POST("{}");
    Serial.printf("[HTTP] EXIT → %d\n", code);
    http.end();
  }
}

// ─── WiFi ─────────────────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.printf("\n[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.printf("\n[WiFi] Connected — IP: %s\n", WiFi.localIP().toString().c_str());
  Serial.printf("[INFO] Backend will call: http://%s/door/scan|open|deny\n",
                WiFi.localIP().toString().c_str());
  Serial.printf("[INFO] Copy URL above to Devices page → esp8266_url field\n");
}

// ─── setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);

  pinMode(RELAY,     OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_RED,   OUTPUT);
  pinMode(BUZZER,    OUTPUT);
  pinMode(BUTTON,    INPUT_PULLUP);

  enterIdle();  // safe state: lock door, red LED on

  connectWiFi();

  server.on("/door/scan", HTTP_POST, handleDoorScan);
  server.on("/door/open", HTTP_POST, handleDoorOpen);
  server.on("/door/deny", HTTP_POST, handleDoorDeny);
  // Handle CORS preflight from browser
  server.on("/door/scan", HTTP_OPTIONS, handleOptions);
  server.on("/door/open", HTTP_OPTIONS, handleOptions);
  server.on("/door/deny", HTTP_OPTIONS, handleOptions);
  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("[DOOR] Web server started — ready for backend commands");
}

// ─── loop ─────────────────────────────────────────────────────────────────────
void loop() {
  server.handleClient();  // serve incoming HTTP from backend

  unsigned long now = millis();

  // ── Button debounced read ──────────────────────────────────────────────────
  bool btnLow = (digitalRead(BUTTON) == LOW);
  if (btnLow && !buttonWasLow && (now - lastBtnTime > BTN_DEBOUNCE_MS)) {
    lastBtnTime     = now;
    buttonWasLow    = true;
    Serial.println("[BTN] Exit pressed");
    enterExit();            // relay releases IMMEDIATELY
    pendingExitHttp = true; // HTTP sent next loop() — non-blocking
  }
  if (!btnLow) buttonWasLow = false;

  // ── Deferred exit HTTP ────────────────────────────────────────────────────
  if (pendingExitHttp) {
    pendingExitHttp = false;
    sendExitRequest();
  }

  // ── State machine tick ────────────────────────────────────────────────────
  switch (state) {

    case IDLE:
      break;

    case SCANNING:
      if (now - lastBlinkMs >= 200) {
        lastBlinkMs = now;
        blinkState  = !blinkState;
        digitalWrite(LED_RED, blinkState ? HIGH : LOW);
      }
      if (now - stateTimer > SCAN_TIMEOUT_MS) {
        Serial.println("[DOOR] Scan timeout — reverting to IDLE");
        enterIdle();
      }
      break;

    case GRANTED:
      if (now - stateTimer > UNLOCK_MS) enterIdle();
      break;

    case DENIED:
      if (now - lastBlinkMs >= 100) {
        lastBlinkMs = now;
        blinkState  = !blinkState;
        digitalWrite(LED_RED, blinkState ? HIGH : LOW);
      }
      if (now - stateTimer > DENIED_BLINK_MS) enterIdle();
      break;

    case EXIT_OPEN:
      if (now - stateTimer > UNLOCK_MS) enterIdle();
      break;
  }
}
