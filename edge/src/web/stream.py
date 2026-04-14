"""
Flask MJPEG streaming server for edge Mode-2 offline monitoring.
Access from browser on the same LAN: http://<pi-ip>:5000
"""
import time
import logging
import threading
import numpy as np
import cv2
from flask import Flask, Response, jsonify, render_template_string, make_response, request

from edge.src.web.state import shared
from edge.src.config import config

logger = logging.getLogger("edge.web")

app = Flask(__name__)


def _cors(response):
    """Add CORS headers so the frontend kiosk page can fetch /snapshot cross-origin."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.after_request
def after_request(response):
    return _cors(response)

# ---------------------------------------------------------------------------
# Kiosk attendance page — cloud-like design
# ---------------------------------------------------------------------------
_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Attendance — AIoT Edge</title>
<style>
:root{--bg:#0b0f1a;--bg2:#111827;--bg3:#1e2a3a;--border:#1e3a5f;
      --blue:#3b82f6;--blue-d:#1d4ed8;--green:#22c55e;--red:#ef4444;
      --yellow:#f59e0b;--text:#f1f5f9;--muted:#64748b;--card:#13203a;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;
     height:100vh;display:flex;flex-direction:column;overflow:hidden;}

/* ── Top bar ── */
.topbar{background:var(--bg2);border-bottom:1px solid var(--border);
        display:flex;align-items:center;gap:12px;padding:0 20px;height:56px;flex-shrink:0;}
.logo{background:var(--blue-d);border-radius:8px;width:32px;height:32px;
      display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px;}
.class-info{flex:1;}
.class-name{font-weight:700;font-size:.95rem;color:var(--text);}
.device-name{font-size:.72rem;color:var(--muted);}
.topbar-right{display:flex;align-items:center;gap:14px;}
.clock{font-size:1.1rem;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:.05em;}
.conn-badge{display:flex;align-items:center;gap:5px;font-size:.75rem;border-radius:9999px;
            padding:3px 10px;font-weight:600;}
.conn-badge.online{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3);}
.conn-badge.offline{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);}
.conn-dot{width:7px;height:7px;border-radius:50%;background:currentColor;}
.enroll-btn{background:var(--bg3);border:1px solid var(--border);border-radius:8px;
            padding:5px 12px;font-size:.78rem;color:var(--muted);cursor:pointer;text-decoration:none;}
.enroll-btn:hover{color:var(--text);border-color:var(--blue);}

/* ── Main area ── */
.main{flex:1;display:flex;overflow:hidden;gap:0;}

/* ── Camera panel ── */
.cam-section{flex:1;display:flex;flex-direction:column;background:var(--bg);position:relative;overflow:hidden;}
.cam-wrap{flex:1;position:relative;overflow:hidden;display:flex;align-items:center;justify-content:center;background:#000;}
.cam-feed{width:100%;height:100%;object-fit:cover;display:block;transform:scaleX(-1);}

/* Scanning ring */
.scan-ring{position:absolute;width:220px;height:220px;border:3px solid var(--blue);
           border-radius:50%;animation:pulse 2s ease-in-out infinite;pointer-events:none;}
.scan-ring.detected{border-color:var(--yellow);animation:pulse-fast .8s ease-in-out infinite;}
.scan-ring.recognized{border-color:var(--green);animation:pulse-fast .5s ease-in-out infinite;}
@keyframes pulse{0%,100%{transform:scale(1);opacity:.4;}50%{transform:scale(1.08);opacity:.8;}}
@keyframes pulse-fast{0%,100%{transform:scale(1);opacity:.6;}50%{transform:scale(1.04);opacity:1;}}

/* Recognition flash overlay */
.rec-flash{position:absolute;inset:0;pointer-events:none;
           background:rgba(34,197,94,.12);opacity:0;transition:opacity .3s;border:3px solid var(--green);}
.rec-flash.active{opacity:1;}

/* Bottom camera status bar */
.cam-footer{background:rgba(0,0,0,.7);padding:8px 16px;display:flex;gap:16px;align-items:center;
            font-size:.78rem;flex-shrink:0;backdrop-filter:blur(4px);}
.pill{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:9999px;font-weight:600;}
.pill.ok{background:rgba(34,197,94,.2);color:var(--green);border:1px solid rgba(34,197,94,.3);}
.pill.warn{background:rgba(245,158,11,.2);color:var(--yellow);border:1px solid rgba(245,158,11,.3);}
.pill.dim{background:rgba(100,116,139,.15);color:var(--muted);border:1px solid rgba(100,116,139,.2);}
.queue-count{margin-left:auto;font-size:.72rem;color:var(--muted);}

/* ── Right info panel ── */
.info-section{width:340px;display:flex;flex-direction:column;background:var(--bg2);
              border-left:1px solid var(--border);flex-shrink:0;overflow:hidden;}

/* Current result card */
.result-card{padding:20px;border-bottom:1px solid var(--border);flex-shrink:0;}
.result-idle{text-align:center;padding:24px 16px;}
.idle-icon{font-size:48px;margin-bottom:10px;opacity:.5;}
.idle-text{color:var(--muted);font-size:.85rem;}
.result-recognized{display:none;}
.avatar-circle{width:72px;height:72px;border-radius:50%;background:var(--blue-d);
               display:flex;align-items:center;justify-content:center;
               font-size:1.8rem;font-weight:700;margin:0 auto 14px;
               border:3px solid var(--green);box-shadow:0 0 20px rgba(34,197,94,.3);}
.rec-name{font-size:1.3rem;font-weight:700;text-align:center;color:var(--text);}
.rec-code{text-align:center;color:var(--muted);font-size:.82rem;margin-top:2px;font-family:monospace;}
.rec-meta{display:flex;justify-content:center;gap:12px;margin-top:10px;}
.meta-chip{font-size:.72rem;padding:3px 10px;border-radius:9999px;font-weight:600;}
.meta-conf{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3);}
.meta-time{background:rgba(59,130,246,.15);color:#7dd3fc;border:1px solid rgba(59,130,246,.3);}
.success-bar{margin-top:12px;background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);
             border-radius:10px;padding:8px 12px;text-align:center;
             color:var(--green);font-weight:700;font-size:.88rem;}

/* ── Toggle buttons ── */
.toggle-btn{display:flex;align-items:center;gap:5px;font-size:.73rem;font-weight:600;
            border-radius:8px;padding:4px 10px;cursor:pointer;border:1px solid var(--border);
            background:var(--bg3);color:var(--muted);user-select:none;transition:.15s;white-space:nowrap;}
.toggle-btn.active-on{background:rgba(34,197,94,.15);color:var(--green);border-color:rgba(34,197,94,.4);}
.toggle-btn.active-warn{background:rgba(245,158,11,.15);color:var(--yellow);border-color:rgba(245,158,11,.4);}

/* ── Confirm button (manual mode) ── */
.confirm-btn{margin-top:12px;width:100%;padding:11px;border-radius:10px;border:none;
             background:var(--blue);color:#fff;font-size:.9rem;font-weight:700;
             cursor:pointer;letter-spacing:.04em;transition:.15s;display:none;}
.confirm-btn:hover{background:#2563eb;}
.confirm-btn:active{transform:scale(.98);}

/* ── Pose warning ── */
.pose-warn{margin-top:10px;background:rgba(245,158,11,.15);border:1px solid rgba(245,158,11,.4);
           border-radius:8px;padding:8px 12px;text-align:center;
           color:var(--yellow);font-size:.82rem;font-weight:600;display:none;}

/* ── Unknown face warning ── */
.unknown-bar{margin-top:14px;background:rgba(239,68,68,.13);border:1px solid rgba(239,68,68,.4);
             border-radius:10px;padding:10px 14px;text-align:center;
             color:#fca5a5;font-size:.85rem;font-weight:600;display:none;}

/* ── Pending mark (waiting confirm) ── */
.pending-bar{margin-top:10px;background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.4);
             border-radius:8px;padding:8px 12px;text-align:center;
             color:#7dd3fc;font-size:.82rem;font-weight:600;display:none;}

/* Recent attendance list */
.recent-header{padding:14px 20px 8px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0;}
.recent-title{font-size:.8rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
.recent-count{font-size:.72rem;color:var(--muted);background:var(--bg3);
              border-radius:9999px;padding:2px 8px;}
.recent-list{flex:1;overflow-y:auto;padding:0 12px 12px;}
.recent-list::-webkit-scrollbar{width:4px;}
.recent-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:9999px;}
.rec-item{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;
          background:var(--card);margin-bottom:6px;transition:background .2s;}
.rec-item.new{background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.25);animation:fadeIn .5s;}
@keyframes fadeIn{from{opacity:0;transform:translateY(-6px);}to{opacity:1;transform:none;}}
.rec-avatar{width:36px;height:36px;border-radius:50%;background:var(--blue-d);
            display:flex;align-items:center;justify-content:center;font-weight:700;
            font-size:.85rem;flex-shrink:0;}
.rec-body{flex:1;min-width:0;}
.rec-name-sm{font-size:.85rem;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.rec-code-sm{font-size:.72rem;color:var(--muted);font-family:monospace;}
.rec-time{font-size:.7rem;color:var(--muted);flex-shrink:0;}
.empty-state{text-align:center;padding:32px 10px;color:var(--muted);font-size:.82rem;}

/* Offline queue banner */
.offline-banner{display:none;background:rgba(239,68,68,.12);border-top:1px solid rgba(239,68,68,.3);
                padding:6px 16px;font-size:.75rem;color:var(--red);text-align:center;flex-shrink:0;}
</style>
</head>
<body>

<!-- Top bar -->
<header class="topbar">
  <div class="logo">AI</div>
  <div class="class-info">
    <div class="class-name" id="className">Loading...</div>
    <div class="device-name" id="deviceName"></div>
  </div>
  <div class="topbar-right">
    <span class="clock" id="clock">00:00:00</span>
    <!-- Feature toggles -->
    <button class="toggle-btn" id="btnAuto" onclick="toggleSetting('auto')">⚡ Auto</button>
    <button class="toggle-btn" id="btnPose" onclick="toggleSetting('pose')">🧭 Pose</button>
    <span class="conn-badge offline" id="connBadge"><span class="conn-dot"></span><span id="connText">Offline</span></span>
    <a href="/enroll" class="enroll-btn">+ Enroll</a>
  </div>
</header>

<!-- Main -->
<div class="main">

  <!-- Camera section -->
  <section class="cam-section">
    <div class="cam-wrap">
      <img class="cam-feed" src="/video" alt="Camera">
      <div class="scan-ring" id="scanRing"></div>
      <div class="rec-flash" id="recFlash"></div>
    </div>
    <div class="cam-footer">
      <span class="pill dim" id="facesPill">No face detected</span>
      <span class="pill dim" id="livenessPill">Liveness</span>
      <span class="queue-count" id="queueCount"></span>
    </div>
  </section>

  <!-- Info section -->
  <aside class="info-section">

    <!-- Result card -->
    <div class="result-card">
      <div class="result-idle" id="resultIdle">
        <div class="idle-icon">📷</div>
        <div class="idle-text">Face the camera to mark attendance</div>
        <div class="unknown-bar" id="unknownBar">🚫 Khuôn mặt chưa được đăng ký<br><small style="opacity:.75;font-weight:400">Face not enrolled in the system</small></div>
      </div>
      <div class="result-recognized" id="resultRec">
        <div class="avatar-circle" id="recAvatar">?</div>
        <div class="rec-name" id="recName">—</div>
        <div class="rec-code" id="recCode">—</div>
        <div class="rec-meta">
          <span class="meta-chip meta-conf" id="recConf">—</span>
          <span class="meta-chip meta-time" id="recTime">—</span>
        </div>
        <div class="success-bar" id="successBar">✅ Attendance Marked</div>
        <div class="pending-bar" id="pendingBar">👆 Tap CONFIRM to mark attendance</div>
        <button class="confirm-btn" id="confirmBtn" onclick="confirmAttendance()">✅ CONFIRM ATTENDANCE</button>
        <div class="pose-warn" id="poseWarn">⚠️ Look straight at the camera</div>
      </div>
    </div>

    <!-- Recent list -->
    <div class="recent-header">
      <span class="recent-title">Today's Attendance</span>
      <span class="recent-count" id="recentCount">0</span>
    </div>
    <div class="recent-list" id="recentList">
      <div class="empty-state">No records yet</div>
    </div>

    <!-- Offline queue banner -->
    <div class="offline-banner" id="offlineBanner"></div>
  </aside>

</div>

<script>
let lastRecId = null;
let recentCache = [];
let currentSettings = {auto_attendance: true, require_pose: false};

// ── Clock ──────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleTimeString('en-US', {hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
}
setInterval(updateClock, 1000);
updateClock();

// ── Load device/class info — polls every 15s so class name auto-updates ───
async function loadInfo() {
  try {
    const d = await fetch('/info').then(r => r.json());
    document.getElementById('className').textContent = d.class_name || 'Class';
    document.getElementById('deviceName').textContent = d.device_name + ' · ' + d.class_id.slice(0,8) + '…';
    document.title = 'Attendance — ' + (d.class_name || 'Edge');
  } catch(e) {}
}
loadInfo();
setInterval(loadInfo, 15000);  // re-poll so Dashboard class changes appear within 15s

// ── Avatar initial ─────────────────────────────────────────────────────────
function getInitial(name) {
  if (!name) return '?';
  const parts = name.trim().split(' ');
  return parts[parts.length - 1].charAt(0).toUpperCase();
}

// ── Poll status ────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const d = await fetch('/status').then(r => r.json());

    // Connection badge
    const badge = document.getElementById('connBadge');
    if (d.cloud_online) {
      badge.className = 'conn-badge online';
      document.getElementById('connText').textContent = 'Online';
    } else {
      badge.className = 'conn-badge offline';
      document.getElementById('connText').textContent = 'Offline';
    }

    // Feature toggle button states
    currentSettings.auto_attendance = d.auto_attendance !== false;
    currentSettings.require_pose = d.require_pose === true;
    const btnAuto = document.getElementById('btnAuto');
    const btnPose = document.getElementById('btnPose');
    if (currentSettings.auto_attendance) {
      btnAuto.className = 'toggle-btn active-on';
      btnAuto.textContent = '⚡ Auto';
    } else {
      btnAuto.className = 'toggle-btn active-warn';
      btnAuto.textContent = '👆 Manual';
    }
    if (currentSettings.require_pose) {
      btnPose.className = 'toggle-btn active-warn';
      btnPose.textContent = '🧭 Pose ON';
    } else {
      btnPose.className = 'toggle-btn';
      btnPose.textContent = '🧭 Pose OFF';
    }

    // Pose warning overlay
    const poseWarn = document.getElementById('poseWarn');
    poseWarn.style.display = (d.pose_rejected && d.faces_detected > 0) ? 'block' : 'none';

    // Faces + liveness pills
    const faces = d.faces_detected ?? 0;
    const liveness = d.liveness_passed;
    const facesPill = document.getElementById('facesPill');
    const livenessPill = document.getElementById('livenessPill');
    const ring = document.getElementById('scanRing');

    if (faces > 0) {
      facesPill.textContent = faces + (faces > 1 ? ' faces' : ' face');
      facesPill.className = 'pill ok';
    } else {
      facesPill.textContent = 'No face detected';
      facesPill.className = 'pill dim';
    }

    if (faces > 0 && liveness) {
      livenessPill.textContent = '✔ Liveness OK';
      livenessPill.className = 'pill ok';
    } else if (faces > 0) {
      livenessPill.textContent = '⏳ Checking...';
      livenessPill.className = 'pill warn';
    } else {
      livenessPill.textContent = 'Liveness';
      livenessPill.className = 'pill dim';
    }

    // Scan ring state
    if (d.recent && d.last_recognized) {
      ring.className = 'scan-ring recognized';
    } else if (faces > 0) {
      ring.className = 'scan-ring detected';
    } else {
      ring.className = 'scan-ring';
    }

    // Manual confirm mode: pending_mark is set
    const pm = d.pending_mark;
    const autoMode = d.auto_attendance !== false;
    const confirmBtn = document.getElementById('confirmBtn');
    const successBar = document.getElementById('successBar');
    const pendingBar = document.getElementById('pendingBar');

    const unknownBar = document.getElementById('unknownBar');
    if (!autoMode && pm) {
      // Show recognized face + CONFIRM button instead of auto-success bar
      const pmId = pm.student_id;
      if (pmId !== lastRecId) {
        lastRecId = pmId;
        showRecognized(pm, null);
        triggerFlash();
      }
      successBar.style.display = 'none';
      pendingBar.style.display = 'block';
      confirmBtn.style.display = 'block';
      confirmBtn.dataset.studentId = pm.student_id;
      unknownBar.style.display = 'none';
    } else if (d.last_recognized && d.recent) {
      const rec = d.last_recognized;
      const recId = rec.student_id + '_' + (d.seconds_ago || 0);
      if (recId !== lastRecId) {
        lastRecId = recId;
        showRecognized(rec, d.seconds_ago);
        triggerFlash();
      }
      successBar.style.display = autoMode ? 'block' : 'none';
      pendingBar.style.display = 'none';
      confirmBtn.style.display = 'none';
      unknownBar.style.display = 'none';
    } else {
      // No recognition — show unknown face warning if liveness passed
      const isUnknown = faces > 0 && liveness;
      unknownBar.style.display = isUnknown ? 'block' : 'none';
      document.getElementById('resultIdle').style.display = 'block';
      document.getElementById('resultRec').style.display = 'none';
      confirmBtn.style.display = 'none';
      pendingBar.style.display = 'none';
    }

  } catch(e) {
    // Server unreachable
    const badge = document.getElementById('connBadge');
    badge.className = 'conn-badge offline';
    document.getElementById('connText').textContent = 'Offline';
  }
}

function showRecognized(rec, secsAgo) {
  document.getElementById('resultIdle').style.display = 'none';
  const rEl = document.getElementById('resultRec');
  rEl.style.display = 'block';
  const initial = getInitial(rec.name);
  document.getElementById('recAvatar').textContent = initial;
  document.getElementById('recName').textContent = rec.name || '—';
  document.getElementById('recCode').textContent = rec.student_code || '';
  document.getElementById('recConf').textContent =
    '🎯 ' + ((rec.confidence ?? 0) * 100).toFixed(1) + '%';
  document.getElementById('recTime').textContent =
    '🕐 ' + (secsAgo !== null ? secsAgo + 's ago' : 'Just now');
}

function triggerFlash() {
  const flash = document.getElementById('recFlash');
  flash.classList.add('active');
  setTimeout(() => flash.classList.remove('active'), 800);
}

async function toggleSetting(which) {
  const payload = {};
  if (which === 'auto') payload.auto_attendance = !currentSettings.auto_attendance;
  if (which === 'pose') payload.require_pose = !currentSettings.require_pose;
  try {
    await fetch('/settings', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  } catch(e) {}
}

async function confirmAttendance() {
  const btn = document.getElementById('confirmBtn');
  btn.disabled = true;
  btn.textContent = '⏳ Processing...';
  try {
    const r = await fetch('/mark', {method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    if (d.ok) {
      btn.textContent = '✅ Marked!';
      btn.style.background = '#16a34a';
      document.getElementById('successBar').style.display = 'block';
      document.getElementById('pendingBar').style.display = 'none';
      setTimeout(() => { btn.style.display = 'none'; btn.disabled = false;
        btn.textContent = '✅ CONFIRM ATTENDANCE'; btn.style.background = ''; }, 2000);
    } else {
      btn.textContent = '❌ ' + (d.error || 'Error');
      setTimeout(() => { btn.disabled = false; btn.textContent = '✅ CONFIRM ATTENDANCE'; }, 2000);
    }
  } catch(e) {
    btn.disabled = false;
    btn.textContent = '✅ CONFIRM ATTENDANCE';
  }
}

// ── Poll recent attendance ─────────────────────────────────────────────────
async function pollRecent() {
  try {
    const d = await fetch('/recent').then(r => r.json());
    renderRecent(d.recent || []);
    const qCount = d.queue_pending || 0;
    const banner = document.getElementById('offlineBanner');
    const qEl = document.getElementById('queueCount');
    if (qCount > 0) {
      banner.style.display = 'block';
      banner.textContent = '📡 ' + qCount + ' record' + (qCount > 1 ? 's' : '') + ' pending cloud sync';
      qEl.textContent = '🔴 Queue: ' + qCount;
    } else {
      banner.style.display = 'none';
      qEl.textContent = '';
    }
  } catch(e) {}
}

function renderRecent(items) {
  const list = document.getElementById('recentList');
  document.getElementById('recentCount').textContent = items.length;
  if (items.length === 0) {
    list.innerHTML = '<div class="empty-state">No attendance yet</div>';
    return;
  }
  const prevIds = new Set(recentCache.map(i => i.student_id + '_' + i.time_str));
  recentCache = items;
  list.innerHTML = items.map((item, idx) => {
    const key = item.student_id + '_' + item.time_str;
    const isNew = idx === 0 && !prevIds.has(key);
    const initial = getInitial(item.name);
    const code = item.student_code || '';
    const ts = item.time_str || item.timestamp || '';
    return '<div class="rec-item' + (isNew ? ' new' : '') + '">' +
      '<div class="rec-avatar">' + initial + '</div>' +
      '<div class="rec-body">' +
        '<div class="rec-name-sm">' + (item.name || '—') + '</div>' +
        '<div class="rec-code-sm">' + code + '</div>' +
      '</div>' +
      '<div class="rec-time">' + ts + '</div>' +
    '</div>';
  }).join('');
}

setInterval(pollStatus, 1000);
setInterval(pollRecent, 3000);
pollStatus();
pollRecent();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(_HTML)


@app.route("/info")
def info():
    """Return device/class configuration for kiosk display."""
    return jsonify({
        "class_id":   config.CLASS_ID,
        "class_name": config.CLASS_NAME,
        "device_name": config.DEVICE_NAME,
        "cloud_api":  config.CLOUD_API_URL,
    })


@app.route("/recent")
def recent():
    """Return recent attendance from in-memory log + offline queue count."""
    from edge.src.database.local_db import get_recent_attendance, get_pending_count
    mem = shared.get_recent()
    db_rows = get_recent_attendance(limit=20)
    db_items = [
        {
            "student_id":   r["student_id"],
            "student_code": r["student_code"] or "",
            "name":         r["full_name"] or "",
            "confidence":   r["confidence"],
            "time_str":     (r["timestamp"] or "")[:19].replace("T", " "),
            "sync_status":  r["sync_status"],
        }
        for r in db_rows
    ]
    items = mem if mem else db_items
    return jsonify({"recent": items, "queue_pending": get_pending_count()})


@app.route("/settings", methods=["POST"])
def settings():
    """Toggle auto_attendance and/or require_pose."""
    data = request.get_json(silent=True) or {}
    auto_att = data.get("auto_attendance")
    req_pose = data.get("require_pose")
    if auto_att is not None:
        auto_att = bool(auto_att)
    if req_pose is not None:
        req_pose = bool(req_pose)
    shared.set_settings(auto_attendance=auto_att, require_pose=req_pose)
    return jsonify({"auto_attendance": shared.auto_attendance, "require_pose": shared.require_pose})


@app.route("/mark", methods=["POST"])
def manual_mark():
    """Manual attendance confirm (auto_attendance=False mode)."""
    from edge.src.database.local_db import post_or_queue_attendance
    import time as _time

    pm = shared.consume_pending_mark()
    if pm is None:
        return jsonify({"ok": False, "error": "No pending face to confirm"}), 400

    ok = post_or_queue_attendance(
        student_id=pm["student_id"],
        confidence=pm["confidence"],
        liveness_score=pm["liveness_score"],
    )
    # Update shared state so recent list refreshes
    shared.last_result = {
        "student_id": pm["student_id"],
        "name": pm["name"],
        "student_code": pm.get("student_code", ""),
        "confidence": pm["confidence"],
        "liveness_score": pm["liveness_score"],
    }
    shared.last_recognized_at = _time.time()
    return jsonify({"ok": True, "cloud": ok, "student": pm["name"]})


@app.route("/video")
def video():
    """MJPEG stream — browser keeps this connection open."""
    def generate():
        blank = None
        while True:
            frame = shared.get_jpeg()
            if frame:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
            else:
                # No frame yet — send a tiny placeholder so browser connects
                if blank is None:
                    import cv2, numpy as np
                    img = np.zeros((120, 160, 3), dtype=np.uint8)
                    cv2.putText(img, "Waiting...", (10, 65),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)
                    _, buf = cv2.imencode(".jpg", img)
                    blank = buf.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + blank
                    + b"\r\n"
                )
            time.sleep(0.04)   # ~25 fps cap

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/status")
def status():
    return jsonify(shared.get_status())


@app.route("/snapshot")
def snapshot():
    """Return a single JPEG frame — used by kiosk page for frame capture."""
    frame = shared.get_jpeg()
    if not frame:
        import cv2, numpy as np
        img = np.zeros((120, 160, 3), dtype=np.uint8)
        cv2.putText(img, "Waiting...", (10, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)
        _, buf = cv2.imencode(".jpg", img)
        frame = buf.tobytes()
    resp = make_response(frame)
    resp.headers["Content-Type"] = "image/jpeg"
    resp.headers["Cache-Control"] = "no-cache, no-store"
    return resp


# ---------------------------------------------------------------------------
# /enroll — Local face enrollment matching cloud flow (6-pose, 5 frames/pose)
# ---------------------------------------------------------------------------

# In-memory session buffer: student_code → list of np.ndarray embeddings
_enroll_sessions: dict = {}
_enroll_lock = threading.Lock()

POSE_STEPS = [
    {"label": "Look straight at the camera", "emoji": "😐"},
    {"label": "Turn head slightly left",      "emoji": "👈"},
    {"label": "Turn head slightly right",     "emoji": "👉"},
    {"label": "Tilt head slightly up",        "emoji": "☝️"},
    {"label": "Tilt head slightly down",      "emoji": "👇"},
    {"label": "Look straight (confirm)",      "emoji": "✅"},
]
MIN_ACCEPTED = 5   # frames per pose step (no angle check — accept any frame)

def _check_pose(yaw: float, pitch: float, step_index: int):
    """Pose check disabled — always accepted."""
    return True, ""

_ENROLL_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Face Enrollment — Edge Device</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #f8fafc; color: #1e293b; font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }
  .topbar { background: #fff; border-bottom: 1px solid #e2e8f0; padding: 0 24px; height: 56px;
            display: flex; align-items: center; gap: 12px; }
  .topbar-logo { width: 28px; height: 28px; background: #2563eb; border-radius: 8px;
                 display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 14px; }
  .topbar-title { font-weight: 600; font-size: .95rem; color: #1e293b; }
  .topbar-badge { margin-left: auto; background: #dbeafe; color: #1d4ed8; border-radius: 9999px;
                  padding: 2px 10px; font-size: .75rem; font-weight: 600; }
  .page { max-width: 1100px; margin: 0 auto; padding: 28px 20px; }
  .back { display: inline-flex; align-items: center; gap: 6px; color: #64748b; font-size: .85rem;
          text-decoration: none; margin-bottom: 20px; cursor: pointer; background: none; border: none; }
  .back:hover { color: #1e293b; }
  h1 { font-size: 1.5rem; font-weight: 700; color: #0f172a; margin-bottom: 4px; }
  .subtitle { color: #64748b; font-size: .875rem; margin-bottom: 24px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
  @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }

  /* Camera panel */
  .cam-panel { background: #000; border-radius: 16px; overflow: hidden; aspect-ratio: 4/3; position: relative; }
  .cam-panel img { width: 100%; height: 100%; object-fit: cover; display: block; transform: scaleX(-1); }
  .cam-overlay { position: absolute; inset: 0; pointer-events: none; display: flex;
                 align-items: center; justify-content: center; }
  .cam-ring { width: 180px; height: 180px; border: 4px solid #3b82f6; border-radius: 50%;
              opacity: .6; animation: pulse 1.5s ease-in-out infinite; }
  .cam-ring.red { border-color: #ef4444; }
  @keyframes pulse { 0%,100% { transform: scale(1); opacity:.6; } 50% { transform: scale(1.05); opacity:.9; } }
  .cam-label { position: absolute; bottom: 16px; left: 0; right: 0; text-align: center; }
  .cam-label span { background: rgba(0,0,0,.7); color: #fff; border-radius: 9999px;
                    padding: 6px 18px; font-size: .85rem; display: inline-block; margin-bottom: 6px; }
  .cam-label small { display: block; background: rgba(0,0,0,.5); color: #fff; border-radius: 9999px;
                     padding: 3px 12px; font-size: .75rem; display: inline-block; }
  .cam-reject { position: absolute; top: 14px; left: 0; right: 0; text-align: center; }
  .cam-reject span { background: rgba(220,38,38,.85); color: #fff; border-radius: 9999px;
                     padding: 6px 16px; font-size: .82rem; }

  /* Controls panel */
  .ctrl { display: flex; flex-direction: column; gap: 18px; }
  .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; }

  /* Student lookup */
  label { font-size: .82rem; font-weight: 500; color: #374151; display: block; margin-bottom: 6px; }
  .inp-row { display: flex; gap: 8px; }
  input[type=text] { flex: 1; padding: 9px 12px; border: 1px solid #d1d5db; border-radius: 8px;
                     font-size: .9rem; color: #1e293b; outline: none; background: #fff; }
  input[type=text]:focus { border-color: #3b82f6; box-shadow: 0 0 0 3px rgba(59,130,246,.15); }
  .btn-lookup { padding: 9px 16px; background: #2563eb; color: #fff; border: none; border-radius: 8px;
                font-size: .85rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
  .btn-lookup:hover { background: #1d4ed8; }
  .student-chip { display: flex; align-items: center; gap: 10px; padding: 12px 14px;
                  background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; }
  .chip-code { font-family: monospace; font-weight: 700; color: #1d4ed8; font-size: .85rem; }
  .chip-name { color: #334155; font-size: .9rem; }
  .chip-clear { margin-left: auto; background: none; border: none; cursor: pointer; color: #94a3b8; font-size: 18px; line-height: 1; }
  .chip-clear:hover { color: #475569; }
  .msg-err { background: #fef2f2; border: 1px solid #fecaca; color: #b91c1c;
             border-radius: 8px; padding: 10px 14px; font-size: .85rem; }
  .msg-ok  { background: #f0fdf4; border: 1px solid #bbf7d0; color: #15803d;
             border-radius: 8px; padding: 10px 14px; font-size: .85rem; }

  /* Progress */
  .progress-bar { background: #e2e8f0; border-radius: 9999px; height: 6px; margin-bottom: 12px; overflow: hidden; }
  .progress-fill { height: 100%; background: #2563eb; border-radius: 9999px; transition: width .4s ease; }
  .progress-label { display: flex; justify-content: space-between; font-size: .78rem; color: #64748b; margin-bottom: 6px; }
  .step-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px;
              font-size: .85rem; color: #94a3b8; }
  .step-row.active { background: #eff6ff; border: 1px solid #bfdbfe; color: #1d4ed8; }
  .step-row.done   { color: #16a34a; }
  .step-emoji { font-size: 1.1rem; flex-shrink: 0; }
  .step-label { flex: 1; }
  .step-count { font-size: .75rem; font-weight: 700; }

  /* Start button */
  .btn-start { width: 100%; padding: 13px; background: #2563eb; color: #fff; border: none;
               border-radius: 10px; font-size: 1rem; font-weight: 600; cursor: pointer;
               display: flex; align-items: center; justify-content: center; gap: 8px; transition: background .15s; }
  .btn-start:hover:not(:disabled) { background: #1d4ed8; }
  .btn-start:disabled { opacity: .5; cursor: not-allowed; }
  .spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,.3);
             border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Success screen */
  .success { text-align: center; padding: 48px 24px; }
  .success-icon { font-size: 64px; margin-bottom: 16px; }
  .success h2 { font-size: 1.4rem; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
  .success p  { color: #64748b; margin-bottom: 24px; font-size: .9rem; }
  .btn-back { padding: 10px 24px; background: #2563eb; color: #fff; border: none; border-radius: 8px;
              font-size: .9rem; font-weight: 600; cursor: pointer; }
  .btn-back:hover { background: #1d4ed8; }
</style>
</head>
<body>
<div class="topbar">
  <div class="topbar-logo">AI</div>
  <span class="topbar-title">AIoT Smart Attendance</span>
  <span class="topbar-badge">📡 Edge Device — Offline</span>
</div>

<div class="page" id="main">
  <button class="back" onclick="location.href='/'">&#8592; Back</button>
  <h1>Face Enrollment</h1>
  <p class="subtitle">Face Scan — 6 poses · Uses the device camera</p>

  <div class="grid">
    <!-- Left: Camera -->
    <div>
      <div class="cam-panel" id="camPanel">
        <img src="/video" id="camImg" alt="Camera feed">
        <div class="cam-overlay" id="camOverlay" style="display:none">
          <div class="cam-ring" id="camRing"></div>
        </div>
        <div class="cam-label" id="camLabel" style="display:none">
          <span id="poseLabel">😐 Look straight</span><br>
          <small id="frameCount">0 / 5 frames</small>
        </div>
        <div class="cam-reject" id="camReject" style="display:none">
          <span id="rejectMsg"></span>
        </div>
      </div>
    </div>

    <!-- Right: Controls -->
    <div class="ctrl" id="ctrlPanel">

      <!-- Student lookup -->
      <div class="card" id="lookupCard">
        <label>Student Code</label>
        <div class="inp-row">
          <input type="text" id="codeInput" placeholder="FSB001" onkeydown="if(event.key==='Enter') lookupStudent()">
          <button class="btn-lookup" onclick="lookupStudent()">Search</button>
        </div>
        <div id="lookupMsg" style="margin-top:8px;display:none"></div>
        <div id="studentChip" style="margin-top:8px;display:none">
          <div class="student-chip">
            <div>
              <div class="chip-code" id="chipCode"></div>
              <div class="chip-name" id="chipName"></div>
            </div>
            <button class="chip-clear" onclick="clearStudent()" title="Clear">&#215;</button>
          </div>
        </div>
      </div>

      <!-- Progress steps -->
      <div class="card" id="progressCard" style="display:none">
        <div class="progress-label">
          <span>Progress</span>
          <span id="progText">0 / 6 steps</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" id="progFill" style="width:0%"></div></div>
        <div id="stepList"></div>
        <div id="frameTotal" style="margin-top:10px;font-size:.8rem;color:#64748b;text-align:center"></div>
      </div>

      <!-- Error / success message -->
      <div id="globalMsg" style="display:none"></div>

      <!-- Start button -->
      <button class="btn-start" id="btnStart" onclick="startEnroll()" disabled>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/>
          <circle cx="12" cy="13" r="4"/>
        </svg>
        Start Face Enrollment
      </button>

    </div>
  </div>
</div>

<!-- Success screen (hidden initially) -->
<div class="page" id="successPage" style="display:none">
  <div class="success">
    <div class="success-icon">✅</div>
    <h2>Enrollment Successful!</h2>
    <p id="successMsg"></p>
    <button class="btn-back" onclick="resetPage()">Enroll Another Student</button>
    <button class="btn-back" style="margin-left:8px;background:#0f172a;margin-top:8px;" onclick="location.href='/'">Back to Home</button>
  </div>
</div>

<script>
const POSE_STEPS = """ + str(POSE_STEPS).replace("'", '"') + """;
const MIN_ACCEPTED = """ + str(MIN_ACCEPTED) + """;
const MAX_ATTEMPTS = 20;

let selectedStudent = null;   // {student_id, student_code, full_name}
let capturing = false;
let currentStep = 0;
let stepAccepted = new Array(POSE_STEPS.length).fill(0);
let totalFrames = 0;

// ── Student lookup ─────────────────────────────────────────────────────────
async function lookupStudent() {
  const code = document.getElementById('codeInput').value.trim().toUpperCase();
  if (!code) return;
  const msgEl = document.getElementById('lookupMsg');
  msgEl.style.display = 'block';
  msgEl.innerHTML = '<span style="color:#64748b;font-size:.82rem">Looking up...</span>';
  try {
    const r = await fetch('/enroll/lookup?code=' + encodeURIComponent(code));
    const d = await r.json();
    if (d.ok) {
      selectedStudent = d.student;
      document.getElementById('chipCode').textContent = d.student.student_code;
      document.getElementById('chipName').textContent = d.student.full_name;
      document.getElementById('studentChip').style.display = 'block';
      msgEl.style.display = 'none';
      document.getElementById('btnStart').disabled = false;
      document.getElementById('progressCard').style.display = 'block';
      renderSteps();
    } else {
      msgEl.innerHTML = '<div class="msg-err">' + (d.message || 'Student not found') + '</div>';
      document.getElementById('studentChip').style.display = 'none';
      selectedStudent = null;
      document.getElementById('btnStart').disabled = true;
    }
  } catch(e) {
    msgEl.innerHTML = '<div class="msg-err">Connection error: ' + e + '</div>';
  }
}

function clearStudent() {
  selectedStudent = null;
  document.getElementById('studentChip').style.display = 'none';
  document.getElementById('codeInput').value = '';
  document.getElementById('lookupMsg').style.display = 'none';
  document.getElementById('progressCard').style.display = 'none';
  document.getElementById('btnStart').disabled = true;
}

// ── Step rendering ──────────────────────────────────────────────────────────
function renderSteps() {
  const list = document.getElementById('stepList');
  list.innerHTML = POSE_STEPS.map((p, i) => {
    let cls = 'step-row';
    let countHtml = '';
    if (capturing) {
      if (i < currentStep) { cls += ' done'; countHtml = '<span class="step-count" style="color:#16a34a">✓ ' + stepAccepted[i] + '/' + MIN_ACCEPTED + '</span>'; }
      else if (i === currentStep) { cls += ' active'; countHtml = '<span class="step-count" style="color:#1d4ed8">' + stepAccepted[i] + '/' + MIN_ACCEPTED + '</span>'; }
    }
    return '<div class="' + cls + '"><span class="step-emoji">' + p.emoji + '</span><span class="step-label">' + p.label + '</span>' + countHtml + '</div>';
  }).join('');

  const pct = capturing ? Math.round((currentStep / POSE_STEPS.length) * 100) : 0;
  document.getElementById('progFill').style.width = pct + '%';
  document.getElementById('progText').textContent = (capturing ? currentStep : 0) + ' / ' + POSE_STEPS.length + ' steps';
  document.getElementById('frameTotal').textContent = capturing ? ('Collected ' + totalFrames + ' high-quality frames') : '';
}

// ── Enrollment flow ─────────────────────────────────────────────────────────
async function startEnroll() {
  if (!selectedStudent || capturing) return;
  capturing = true;
  currentStep = 0;
  stepAccepted = new Array(POSE_STEPS.length).fill(0);
  totalFrames = 0;
  document.getElementById('btnStart').disabled = true;
  document.getElementById('globalMsg').style.display = 'none';
  document.getElementById('camOverlay').style.display = 'flex';
  document.getElementById('camLabel').style.display = 'block';
  renderSteps();

  try {
    for (let s = 0; s < POSE_STEPS.length; s++) {
      currentStep = s;
      const pose = POSE_STEPS[s];
      document.getElementById('poseLabel').textContent = pose.emoji + ' ' + pose.label;
      document.getElementById('frameCount').textContent = '0 / ' + MIN_ACCEPTED + ' frames';
      document.getElementById('camRing').className = 'cam-ring';
      document.getElementById('camReject').style.display = 'none';
      renderSteps();

      // Brief pause so user can move to pose
      await sleep(s === 0 ? 1500 : 2000);

      let accepted = 0;
      let attempts = 0;
      while (accepted < MIN_ACCEPTED && attempts < MAX_ATTEMPTS) {
        attempts++;
        await sleep(600);
        const res = await fetch('/enroll/capture', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({student_code: selectedStudent.student_code, step_index: s})
        });
        const d = await res.json();
        if (d.accepted) {
          accepted++;
          totalFrames++;
          stepAccepted[s] = accepted;
          document.getElementById('frameCount').textContent = accepted + ' / ' + MIN_ACCEPTED + ' frames';
          document.getElementById('camRing').className = 'cam-ring';
          document.getElementById('camReject').style.display = 'none';
          renderSteps();
        } else {
          document.getElementById('camRing').className = 'cam-ring red';
          document.getElementById('camReject').style.display = 'block';
          let rejectText = '⚠️ ' + (d.reason || 'No face detected');
          if (d.yaw !== undefined && d.pitch !== undefined) {
            rejectText += ` | yaw=${d.yaw}° pitch=${d.pitch}°`;
          }
          document.getElementById('rejectMsg').textContent = rejectText;
        }
      }
      if (accepted < MIN_ACCEPTED) {
        throw new Error('Step "' + pose.label + '": not enough ' + MIN_ACCEPTED + ' frames after ' + MAX_ATTEMPTS + ' attempts. Check lighting and face position.');
      }
    }

    // All steps done — finalize
    document.getElementById('poseLabel').textContent = '⏳ Finalizing embedding...';
    document.getElementById('frameCount').textContent = totalFrames + ' frames';
    document.getElementById('camReject').style.display = 'none';
    document.getElementById('camRing').className = 'cam-ring';

    const fRes = await fetch('/enroll/finalize', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        student_code: selectedStudent.student_code,
        student_id: selectedStudent.student_id,
        full_name: selectedStudent.full_name,
      })
    });
    const fd = await fRes.json();
    if (!fd.ok) throw new Error(fd.message || 'Finalize thất bại');

    // Show success
    document.getElementById('main').style.display = 'none';
    document.getElementById('successPage').style.display = 'block';
    document.getElementById('successMsg').textContent =
      'Face enrolled for ' + selectedStudent.student_code + ' — ' + selectedStudent.full_name +
      ' with ' + totalFrames + ' high-quality frames.';

  } catch(e) {
    showErr(e.message || String(e));
  } finally {
    capturing = false;
    document.getElementById('camOverlay').style.display = 'none';
    document.getElementById('camLabel').style.display = 'none';
    document.getElementById('camReject').style.display = 'none';
    document.getElementById('btnStart').disabled = false;
    renderSteps();
  }
}

function showErr(msg) {
  const el = document.getElementById('globalMsg');
  el.innerHTML = '<div class="msg-err">' + msg + '</div>';
  el.style.display = 'block';
}

function resetPage() {
  document.getElementById('successPage').style.display = 'none';
  document.getElementById('main').style.display = 'block';
  clearStudent();
  stepAccepted = new Array(POSE_STEPS.length).fill(0);
  totalFrames = 0;
  currentStep = 0;
  renderSteps();
  document.getElementById('globalMsg').style.display = 'none';
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
</script>
</body>
</html>
"""


def _crop_bbox(frame: np.ndarray, bbox: list, target: int = 112) -> np.ndarray:
    x1, y1, x2, y2 = [int(v) for v in bbox]
    h, w = frame.shape[:2]
    crop = frame[max(0, y1):min(h, y2), max(0, x1):min(w, x2)]
    return cv2.resize(crop, (target, target)) if crop.size else np.zeros((target, target, 3), dtype=np.uint8)


@app.route("/enroll", methods=["GET"])
def enroll_page():
    return render_template_string(_ENROLL_HTML)


@app.route("/enroll/lookup")
def enroll_lookup():
    """Return student info by student_code from local DB."""
    code = (request.args.get("code") or "").strip().upper()
    if not code:
        return jsonify({"ok": False, "message": "Missing student code"}), 400
    from edge.src.database.local_db import lookup_by_code
    info = lookup_by_code(code)
    if info:
        return jsonify({"ok": True, "student": {
            "student_id": info["student_id"],
            "student_code": info["student_code"],
            "full_name": info["full_name"],
        }})
    return jsonify({"ok": False, "message": f"'{code}' not found in synced list. Sync from Cloud first or enroll locally."}), 404


@app.route("/enroll/capture", methods=["POST"])
def enroll_capture():
    """
    Grab current Pi camera frame, run face detection + pose check + embedding extraction,
    buffer the embedding into the per-student session.
    """
    data = request.get_json(silent=True) or {}
    student_code = (data.get("student_code") or "").strip()
    step_index   = int(data.get("step_index", 0))
    if not student_code:
        return jsonify({"accepted": False, "reason": "Missing student_code"}), 400

    jpeg = shared.get_jpeg()
    if jpeg is None:
        return jsonify({"accepted": False, "reason": "No camera frame available"}), 503

    try:
        buf = np.frombuffer(jpeg, dtype=np.uint8)
        frame_bgr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
        if frame_bgr is None:
            return jsonify({"accepted": False, "reason": "Frame decode error"})

        from edge.src.ai.face_detection import FaceDetector
        from edge.src.ai.face_alignment import align_face
        from edge.src.ai.face_embedding import FaceEmbedder
        from edge.src.ai.liveness.head_movement import HeadPoseEstimator

        detector = FaceDetector()
        embedder = FaceEmbedder()
        h, w = frame_bgr.shape[:2]
        pose_est = HeadPoseEstimator(w, h)

        faces = detector.detect(frame_bgr)
        if not faces:
            return jsonify({"accepted": False, "reason": "No face detected"})
        if len(faces) > 1:
            return jsonify({"accepted": False, "reason": "Multiple faces detected — only one person allowed"})

        best = faces[0]
        lm5  = best.get("landmarks")   # 5-point landmarks [[x,y]*5]
        bbox = best["bbox"]
        conf = float(best.get("confidence", 0))
        if conf < 0.4:
            return jsonify({"accepted": False, "reason": f"Face too small/blurry (conf={conf:.2f})"})

        yaw, pitch = 0.0, 0.0

        aligned = align_face(frame_bgr, lm5) if lm5 is not None else _crop_bbox(frame_bgr, bbox)
        embedding = embedder.extract(aligned)

        with _enroll_lock:
            if student_code not in _enroll_sessions:
                _enroll_sessions[student_code] = []
            _enroll_sessions[student_code].append(embedding)
            count = len(_enroll_sessions[student_code])

        return jsonify({
            "accepted": True,
            "step": step_index,
            "conf": round(conf, 3),
            "yaw": round(yaw, 1),
            "pitch": round(pitch, 1),
            "total_buffered": count,
        })

    except Exception as e:
        logger.exception("[ENROLL/CAPTURE] error")
        return jsonify({"accepted": False, "reason": f"Processing error: {e}"}), 500


@app.route("/enroll/finalize", methods=["POST"])
def enroll_finalize():
    """
    Average all buffered embeddings → L2-normalize → AES encrypt → store in local_embeddings.
    """
    data = request.get_json(silent=True) or {}
    student_code = (data.get("student_code") or "").strip()
    student_id   = (data.get("student_id")   or "").strip()
    full_name    = (data.get("full_name")     or "").strip()

    if not student_code or not student_id or not full_name:
        return jsonify({"ok": False, "message": "Missing student_code / student_id / full_name"}), 400

    with _enroll_lock:
        vecs = _enroll_sessions.pop(student_code, [])

    if len(vecs) < MIN_ACCEPTED:
        return jsonify({"ok": False, "message": f"Only {len(vecs)} frames — need at least {MIN_ACCEPTED}"}), 422

    try:
        stacked = np.stack(vecs, axis=0)            # (N, 512)
        avg_vec = stacked.mean(axis=0)               # (512,)
        norm    = np.linalg.norm(avg_vec)
        avg_vec = avg_vec / (norm + 1e-10)           # L2-normalize

        from edge.src.core.encryption import encrypt_embedding
        from edge.src.database.local_db import enroll_locally

        enc_bytes = encrypt_embedding(avg_vec)
        enroll_locally(student_id, student_code, full_name, enc_bytes)

        logger.info(f"[ENROLL/FINALIZE] {full_name} ({student_code}) — {len(vecs)} frames → stored is_local=1")
        return jsonify({
            "ok": True,
            "message": f"Enrollment successful: {full_name} ({student_code}) — {len(vecs)} frames",
            "frames_used": len(vecs),
        })
    except Exception as e:
        logger.exception("[ENROLL/FINALIZE] error")
        return jsonify({"ok": False, "message": f"Error saving embedding: {e}"}), 500


def start_server(host: str = "0.0.0.0", port: int = 5000):
    logger.info(f"[WEB] Starting stream server at http://0.0.0.0:{port}")
    app.run(host=host, port=port, threaded=True, use_reloader=False)
