"use client";
export const dynamic = "force-dynamic";

import { useEffect, useRef, useState, useCallback, Suspense } from "react";
import { useParams } from "next/navigation";
import { getApiBase } from "@/lib/api";
import {
  CheckCircle, XCircle, Camera, Loader2,
  RefreshCw, AlertTriangle, Wifi, WifiOff, ShieldAlert,
  ArrowLeft, ArrowRight, ShieldCheck, ShieldOff,
} from "lucide-react";

// ─────────────────────────── Types ───────────────────────────────────────────
type ScanStatus =
  | "idle" | "scanning"
  | "success" | "already" | "unknown" | "no_face" | "liveness_failed" | "error" | "wrong_class";

interface ScanResult {
  matched: boolean;
  student_id?: number;
  student_name?: string;
  student_code?: string;
  confidence: number;
  status: string;
  message: string;
  attendance_id?: number;
}

// ─────────────────────────── Constants ───────────────────────────────────────
const COOLDOWN_MS   = 5000;
const AUTO_SCAN_SEC = 3;

function randomChallenge(): "left" | "right" {
  return Math.random() < 0.5 ? "left" : "right";
}

// ─────────────────────────── Status config ───────────────────────────────────
interface StatusCfg {
  gradient: string; border: string; ovalBorder: string;
  textColor: string; icon: React.ReactNode; title: string;
}
const STATUS_CFG: Record<string, StatusCfg> = {
  success: {
    gradient : "from-green-900/75 to-green-950/85",
    border   : "border-green-400",
    ovalBorder: "border-green-400 shadow-[0_0_50px_14px_rgba(74,222,128,0.40)]",
    textColor: "text-green-300",
    icon     : <CheckCircle className="w-14 h-14 sm:w-20 sm:h-20 text-green-400 drop-shadow-lg" />,
    title    : "",
  },
  already: {
    gradient : "from-blue-900/75 to-blue-950/85",
    border   : "border-blue-400",
    ovalBorder: "border-blue-400 shadow-[0_0_50px_14px_rgba(96,165,250,0.40)]",
    textColor: "text-blue-300",
    icon     : <CheckCircle className="w-14 h-14 sm:w-20 sm:h-20 text-blue-400 drop-shadow-lg" />,
    title    : "Already Checked In",
  },
  unknown: {
    gradient : "from-red-900/75 to-red-950/85",
    border   : "border-red-400",
    ovalBorder: "border-red-400 shadow-[0_0_50px_14px_rgba(248,113,113,0.40)]",
    textColor: "text-red-300",
    icon     : <XCircle className="w-14 h-14 sm:w-20 sm:h-20 text-red-400 drop-shadow-lg" />,
    title    : "Not Recognized",
  },
  no_face: {
    gradient : "from-yellow-900/65 to-yellow-950/75",
    border   : "border-yellow-400",
    ovalBorder: "border-yellow-400 shadow-[0_0_50px_14px_rgba(250,204,21,0.35)]",
    textColor: "text-yellow-300",
    icon     : <AlertTriangle className="w-14 h-14 sm:w-20 sm:h-20 text-yellow-400 drop-shadow-lg" />,
    title    : "No Face Detected",
  },
  liveness_failed: {
    gradient : "from-orange-900/75 to-orange-950/85",
    border   : "border-orange-400",
    ovalBorder: "border-orange-400 shadow-[0_0_50px_14px_rgba(251,146,60,0.40)]",
    textColor: "text-orange-300",
    icon     : <ShieldAlert className="w-14 h-14 sm:w-20 sm:h-20 text-orange-400 drop-shadow-lg" />,
    title    : "Spoofing Detected!",
  },
  error: {
    gradient : "from-gray-800/70 to-gray-950/80",
    border   : "border-gray-500",
    ovalBorder: "border-gray-500",
    textColor: "text-gray-300",
    icon     : <XCircle className="w-14 h-14 sm:w-20 sm:h-20 text-gray-400 drop-shadow-lg" />,
    title    : "Error",
  },
  wrong_class: {
    gradient : "from-purple-900/75 to-purple-950/85",
    border   : "border-purple-400",
    ovalBorder: "border-purple-400 shadow-[0_0_50px_14px_rgba(192,132,252,0.40)]",
    textColor: "text-purple-300",
    icon     : <AlertTriangle className="w-14 h-14 sm:w-20 sm:h-20 text-purple-400 drop-shadow-lg" />,
    title    : "Wrong Class",
  },
  processing: {
    gradient : "from-indigo-900/40 to-indigo-950/60",
    border   : "border-indigo-400/50",
    ovalBorder: "border-indigo-400 shadow-[0_0_50px_10px_rgba(129,140,248,0.25)]",
    textColor: "text-indigo-200",
    icon     : <Loader2 className="w-14 h-14 sm:w-20 sm:h-20 text-indigo-400 animate-spin" />,
    title    : "AI Analysis...",
  },
};

// ─────────────────────────── Main component ───────────────────────────────────
function KioskInner({ classId: classCode }: { classId: string }) {
  // Token + ESP8266 URL stored in localStorage by Devices admin page — never in the URL
  const [token, setToken] = useState("");
  const [espUrl, setEspUrl] = useState("");
  const [tokenLoaded, setTokenLoaded] = useState(false);
  const [numericClassId, setNumericClassId] = useState<number | null>(null);
  const [className, setClassName] = useState("");

  useEffect(() => {
    const tok = localStorage.getItem(`kiosk_token_${classCode}`) ?? "";
    const esp = localStorage.getItem(`kiosk_esp_${classCode}`) ?? "";
    setToken(tok);
    setEspUrl(esp);
    setTokenLoaded(true);
    // Resolve class_code → numeric id + name using device token (no admin JWT needed)
    if (tok) {
      fetch(`${getApiBase()}/api/classes/by-code/${classCode}`, {
        headers: { "X-Device-Token": tok },
      })
        .then((r) => r.json())
        .then((d) => {
          if (d.id) { setNumericClassId(d.id); setClassName(d.class_name); }
        })
        .catch(() => {});
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classCode]);

  // Fire-and-forget call to ESP8266 from browser (same LAN, no Docker isolation)
  // Intentionally silent — Mixed Content block on HTTPS is expected and harmless
  const notifyEsp = useCallback((path: string) => {
    if (!espUrl) return;
    try {
      fetch(`${espUrl.replace(/\/$/, "")}${path}`, { method: "POST" }).catch(() => {});
    } catch { /* Mixed Content or network error — ignore */ }
  }, [espUrl]);

  const videoRef    = useRef<HTMLVideoElement>(null);
  const canvasRef   = useRef<HTMLCanvasElement>(null);
  // Edge stream fallback (when getUserMedia fails — edge container holds the camera)
  const [edgeStreamUrl, setEdgeStreamUrl] = useState<string>("");
  // When true, edge video/snapshot is fetched through the FastAPI backend proxy (for HTTPS kiosk pages)
  const [backendProxyMode, setBackendProxyMode] = useState(false);

  const [camReady, setCamReady]   = useState(false);
  const [camError, setCamError]   = useState<string | null>(null);
  const [scanStatus, setScan]     = useState<ScanStatus>("idle");
  const [result, setResult]       = useState<ScanResult | null>(null);
  const [autoScan, setAutoScan]   = useState(false);
  const [countdown, setCountdown] = useState(AUTO_SCAN_SEC);
  const [online, setOnline]           = useState(true);
  const [challengeEnabled, setChallenge_enabled] = useState(false);
  // Random pose challenge — re-randomised every idle reset
  const [challenge, setChallenge] = useState<"left" | "right">(randomChallenge);

  const base = getApiBase();

  // Network
  useEffect(() => {
    const on  = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online",  on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);

  // ── Device heartbeat — keeps device "Online" while kiosk is open ──────────
  useEffect(() => {
    if (!token) return;
    const beat = () =>
      fetch(`${base}/api/devices/heartbeat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-Token": token },
        body: JSON.stringify({ status: "active" }),
      }).catch(() => {}); // silent — don't disturb kiosk UI on error
    beat(); // immediate on mount
    const iv = setInterval(beat, 30_000); // every 30 s
    return () => clearInterval(iv);
  }, [base, token]);

  // Camera init — tries multiple constraint sets to handle Pi / Linux quirks
  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;

    const tryCamera = async () => {
      // Constraint sets tried in order — broadest last as final fallback
      const constraintSets: MediaStreamConstraints[] = [
        { video: { width: { ideal: 640 }, height: { ideal: 480 } }, audio: false },
        { video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false },
        { video: true, audio: false },
      ];

      // Prefer a real USB/built-in camera — skip virtual/metadata devices
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(
          (d) => d.kind === "videoinput" && d.label !== "" && !d.label.toLowerCase().includes("virtual"),
        );
        if (videoDevices.length > 0) {
          // Insert a deviceId-pinned attempt at the front
          constraintSets.unshift({
            video: {
              deviceId: { exact: videoDevices[0].deviceId },
              width: { ideal: 640 },
              height: { ideal: 480 },
            },
            audio: false,
          });
        }
      } catch { /* enumerateDevices not supported — ignore */ }

      for (const constraints of constraintSets) {
        if (cancelled) return;
        try {
          stream = await navigator.mediaDevices.getUserMedia(constraints);
          break; // got a stream — stop trying
        } catch { /* try next */ }
      }

      if (cancelled) { stream?.getTracks().forEach((t) => t.stop()); return; }

      if (!stream) {
        // getUserMedia failed — try edge MJPEG stream (edge container holds the camera)
        const isHttps = window.location.protocol === "https:";

        if (isHttps) {
          // On HTTPS: direct HTTP probe is blocked by Mixed Content.
          // Use the FastAPI backend as an HTTPS proxy to the edge device.
          const tok = localStorage.getItem(`kiosk_token_${classCode}`) ?? "";
          if (tok) {
            try {
              const probe = await fetch(
                `${base}/api/devices/by-class/${classCode}/edge-snapshot`,
                { headers: { "X-Device-Token": tok } },
              );
              if (probe.ok) {
                if (!cancelled) {
                  setEdgeStreamUrl("proxy");
                  setBackendProxyMode(true);
                  setCamReady(true);
                }
                return;
              }
            } catch { /* backend or edge unreachable */ }
          }
        } else {
          // On HTTP (local LAN): probe the edge container directly
          try {
            const edgeBase = `http://${window.location.hostname}:5000`;
            const probe = await fetch(`${edgeBase}/snapshot`, {
              signal: AbortSignal.timeout ? AbortSignal.timeout(3000) : new AbortController().signal,
            });
            if (probe.ok) {
              if (!cancelled) {
                setEdgeStreamUrl(edgeBase);
                setCamReady(true);
              }
              return;
            }
          } catch { /* edge not available */ }
        }

        setCamError("Cannot access camera.\nCheck camera permissions in your browser.\n\nIf using edge device, ensure edge container is running at port 5000.");
        return;
      }

      if (videoRef.current) {
        const video = videoRef.current;
        video.srcObject = stream;
        try { await video.play(); } catch { /* autoplay may still work silently */ }
        if (!cancelled) setCamReady(true);
      }
    };

    tryCamera();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // ── Scan: capture single frame → backend (ML liveness handled server-side) ───
  const doScan = useCallback(async () => {
    if (!camReady || scanStatus === "scanning") return;
    // In browser-camera mode both refs must be ready; edge mode skips video element
    if (!edgeStreamUrl && (!videoRef.current || !canvasRef.current)) return;

    // Guard: class not resolved yet
    if (numericClassId === null) {
      setResult({ matched: false, confidence: 0, status: "error",
        message: "Class not loaded yet — please wait a moment" });
      setScan("error");
      return;
    }

    setResult(null);
    setScan("scanning");

    // ── Notify ESP8266: scan started → red LED blinks ───────────────────────
    notifyEsp("/door/scan");

    const frames_b64: string[] = [];

    if (edgeStreamUrl) {
      // Edge stream mode: fetch 20 snapshots linearly
      for (let i = 0; i < 20; i++) {
        try {
          const snapResp = backendProxyMode
            ? await fetch(`${base}/api/devices/by-class/${classCode}/edge-snapshot`, {
                headers: { "X-Device-Token": token },
              })
            : await fetch(`${edgeStreamUrl}/snapshot`);
          if (!snapResp.ok) continue;
          const buf = await snapResp.arrayBuffer();
          const bytes = new Uint8Array(buf);
          let binary = "";
          for (let j = 0; j < bytes.byteLength; j++) binary += String.fromCharCode(bytes[j]);
          frames_b64.push(btoa(binary));
        } catch {
          if (frames_b64.length === 0) {
            setResult({ matched: false, confidence: 0, status: "error", message: "Cannot reach edge stream" });
            setScan("error");
            notifyEsp("/door/deny");
            return;
          }
        }
        // Small delay if not in proxy mode. Local edge stream can burst fast.
        await new Promise(r => setTimeout(r, backendProxyMode ? 50 : 100));
      }
    } else {
      // Browser camera mode: Burst 20 frames
      const video = videoRef.current;
      const canvas = canvasRef.current;
      const maxW = 640;
      let w = video.videoWidth || 640;
      let h = video.videoHeight || 480;
      if (w > maxW) {
        h = Math.floor(h * (maxW / w));
        w = maxW;
      }
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) { setScan("error"); return; }

      for (let i = 0; i < 20; i++) {
        ctx.drawImage(video, 0, 0, w, h);
        frames_b64.push(canvas.toDataURL("image/jpeg", 0.70).split(",")[1]);
        await new Promise(r => setTimeout(r, 100)); // 10fps, total ~2.0s
      }
    }

    setScan("processing");

    try {
      const resp = await fetch(`${base}/api/attendance/verify-sequence`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Device-Token": token },
        body: JSON.stringify({ images_b64: frames_b64, class_id: numericClassId }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        // Pydantic 422 returns detail as array of {type,loc,msg,input}; stringify it
        const detail = err.detail;
        const msg: string = typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((e: { msg?: string }) => e.msg ?? JSON.stringify(e)).join("; ")
            : `Server error (${resp.status})`;
        setResult({ matched: false, confidence: 0, status: "error", message: msg });
        setScan("error");
        notifyEsp("/door/deny");
        return;
      }
      const data: ScanResult = await resp.json();
      setResult(data);

      if (data.status === "present" || data.status === "already_marked") {
        notifyEsp("/door/open");
      } else {
        notifyEsp("/door/deny");
      }

      setScan(
        data.status === "present"        ? "success"
        : data.status === "already_marked"  ? "already"
        : data.status === "unknown"         ? "unknown"
        : data.status === "no_face"         ? "no_face"
        : data.status === "liveness_failed" ? "liveness_failed"
        : data.status === "wrong_class"     ? "wrong_class"
        : "error"
      );
    } catch {
      setResult({ matched: false, confidence: 0, status: "error", message: "Server connection lost" });
      setScan("error");
      notifyEsp("/door/deny");
    }
  }, [camReady, scanStatus, base, token, numericClassId, notifyEsp, edgeStreamUrl, backendProxyMode, classCode, challengeEnabled, challenge]);

  // ── Auto-scan state machine ───────────────────────────────────────────────
  useEffect(() => {
    if (!autoScan || !camReady) return;
    if (scanStatus === "scanning") return;

    if (scanStatus !== "idle") {
      const t = setTimeout(() => {
        setScan("idle");
        setResult(null);
        setCountdown(AUTO_SCAN_SEC);
        setChallenge(randomChallenge()); // new direction each cycle
      }, COOLDOWN_MS);
      return () => clearTimeout(t);
    }

    setCountdown(AUTO_SCAN_SEC);
    const intv    = setInterval(() => setCountdown((c) => Math.max(0, c - 1)), 1000);
    const timeout = setTimeout(doScan, AUTO_SCAN_SEC * 1000);
    return () => { clearInterval(intv); clearTimeout(timeout); };
  }, [autoScan, camReady, scanStatus, doScan]);

  // ─── Derived ─────────────────────────────────────────────────────────────
  const isActive   = scanStatus === "scanning";
  const showResult = scanStatus in STATUS_CFG;
  const cfg        = showResult ? STATUS_CFG[scanStatus] : null;

  const ovalCls = isActive
    ? "border-blue-400 shadow-[0_0_50px_14px_rgba(96,165,250,0.45)]"
    : showResult && cfg ? cfg.ovalBorder
    : "border-white/20";

  // ─── Wait for localStorage read (avoid SSR flicker) ──────────────────────
  if (!tokenLoaded) {
    return (
      <div className="fixed inset-0 bg-gray-950 flex items-center justify-center">
        <Loader2 className="w-10 h-10 text-blue-400 animate-spin" />
      </div>
    );
  }

  // ─── No token — device not set up yet ─────────────────────────────────────
  if (!token) {
    return (
      <div className="fixed inset-0 bg-gray-950 flex items-center justify-center p-8">
        <div className="text-center max-w-sm">
          <AlertTriangle className="w-16 h-16 mx-auto mb-4 text-yellow-400" />
          <h1 className="text-2xl font-bold text-white mb-3">Kiosk Not Configured</h1>
          <p className="text-gray-400 text-sm leading-relaxed">
            Go to <span className="text-blue-400 font-medium">Device Management</span>,
            find the device for class <span className="text-white font-mono">{classCode}</span>
            and click <span className="text-green-400 font-medium">Open Kiosk</span>.
          </p>
          <p className="text-gray-600 text-xs mt-4">The kiosk will activate automatically in that tab.</p>
        </div>
      </div>
    );
  }

  // ─── Camera error ─────────────────────────────────────────────────────
  if (camError) {
    return (
      <div className="fixed inset-0 bg-gray-950 flex items-center justify-center p-8">
        <div className="text-center max-w-sm">
          <Camera className="w-16 h-16 text-gray-600 mx-auto mb-4" />
          {camError.split("\n").map((l, i) => <p key={i} className="text-gray-400 text-sm mb-1">{l}</p>)}
          <button onClick={() => window.location.reload()}
            className="mt-5 px-6 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-500 transition-colors">
            Reload Page
          </button>
        </div>
      </div>
    );
  }

  // ─── Full-screen camera kiosk ─────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-black overflow-hidden select-none touch-none">

      {/* Video — browser camera OR edge MJPEG stream */}
      {edgeStreamUrl ? (
        /* Edge stream mode: MJPEG via direct HTTP (LAN) or backend proxy (HTTPS) */
        <img
          src={
            backendProxyMode
              ? `${base}/api/devices/by-class/${classCode}/edge-stream?token=${encodeURIComponent(token)}`
              : `${edgeStreamUrl}/video`
          }
          className="absolute inset-0 w-full h-full object-cover"
          alt="Edge camera stream"
        />
      ) : (
        /* Browser camera mode */
        <video
          ref={videoRef}
          className="absolute inset-0 w-full h-full object-cover"
          style={{ transform: "scaleX(-1)" }}
          muted playsInline autoPlay
        />
      )}

      {/* Camera loading overlay */}
      {!camReady && (
        <div className="absolute inset-0 bg-gray-950 flex flex-col items-center justify-center z-50 gap-3">
          <Loader2 className="w-10 h-10 text-blue-400 animate-spin" />
          <p className="text-gray-400 text-sm">
            {edgeStreamUrl ? "Connecting to edge stream…" : "Starting camera…"}
          </p>
        </div>
      )}

      {/* Gradient vignette — top + bottom for text readability */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-transparent to-black/70 pointer-events-none" />

      {/* Full-screen result tint */}
      {showResult && cfg && (
        <div className={`absolute inset-0 bg-gradient-to-b ${cfg.gradient} backdrop-blur-[2px] pointer-events-none transition-all duration-500`} />
      )}

      {/* ════════ TOP BAR ════════════════════════════════════════════════ */}
      <header className="absolute top-0 left-0 right-0 z-20 flex items-center justify-between px-4 sm:px-8 pt-4 pb-3">
        <div>
          <p className="text-white font-bold text-base sm:text-xl drop-shadow leading-tight">
            🎓 Smart Attendance
          </p>
          <p className="text-white/45 text-xs mt-0.5">{className || classCode}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full bg-black/35 backdrop-blur-sm ${online ? "text-green-400" : "text-red-400"}`}>
            {online ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
            {online ? "Online" : "Offline"}
          </span>
          <button
            onClick={() => { setAutoScan((v) => !v); setScan("idle"); setResult(null); }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-sm transition-all ${
              autoScan ? "bg-green-500/80 text-white" : "bg-black/45 text-white/55 border border-white/20"
            }`}
          >
            <RefreshCw className={`w-3 h-3 ${autoScan ? "animate-spin" : ""}`} />
            {autoScan ? "Auto" : "Manual"}
          </button>
          <button
            onClick={() => setChallenge_enabled((v) => !v)}
            title={challengeEnabled ? "Disable head-turn challenge" : "Enable head-turn challenge"}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold backdrop-blur-sm transition-all ${
              challengeEnabled ? "bg-amber-500/80 text-white" : "bg-black/45 text-white/45 border border-white/20"
            }`}
          >
            {challengeEnabled
              ? <><ShieldCheck className="w-3.5 h-3.5" /> Pose</>  
              : <><ShieldOff   className="w-3.5 h-3.5" /> Pose</>
            }
          </button>
        </div>
      </header>

      {/* ════════ CENTRE — FACE GUIDE ════════════════════════════════════ */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none z-10 px-4">

        {/* Instruction pill above oval */}
        <div className="mb-4 sm:mb-6">
          {!showResult ? (
            <p className="text-white/80 text-xs sm:text-sm font-medium bg-black/30 backdrop-blur-sm px-4 py-1.5 rounded-full text-center">
              {scanStatus === "scanning"
                ? "⚡ Liveness check... Please BLINK!"
                : scanStatus === "processing"
                  ? "🧠 AI Analysis in progress..."
                : autoScan
                  ? `Position your face · auto-scan in ${countdown}s`
                  : "Position your face and press the button below"}
            </p>
          ) : (
            <p className="text-white/50 text-xs bg-black/30 backdrop-blur-sm px-4 py-1.5 rounded-full text-center">
              {autoScan ? `Auto-continuing in ${Math.ceil(COOLDOWN_MS / 1000)}s…` : "Press the button to scan again"}
            </p>
          )}
        </div>

        {/* Challenge arrow — shown only when idle and challenge is enabled */}
        {challengeEnabled && !showResult && !isActive && (
          <div className="flex items-center gap-3 mb-4 px-5 py-2.5 rounded-2xl bg-amber-500/20 border border-amber-400/40 backdrop-blur-sm">
            {challenge === "left" ? (
              <ArrowLeft className="w-7 h-7 text-amber-300 shrink-0" style={{ animation: "pulse 1.2s ease-in-out infinite" }} />
            ) : (
              <ArrowRight className="w-7 h-7 text-amber-300 shrink-0" style={{ animation: "pulse 1.2s ease-in-out infinite" }} />
            )}
            <span className="text-amber-200 text-sm font-semibold tracking-wide">
              {challenge === "left" ? "Turn face to the LEFT" : "Turn face to the RIGHT"}
            </span>
            {challenge === "left" ? (
              <ArrowLeft className="w-7 h-7 text-amber-300 shrink-0" style={{ animation: "pulse 1.2s ease-in-out infinite" }} />
            ) : (
              <ArrowRight className="w-7 h-7 text-amber-300 shrink-0" style={{ animation: "pulse 1.2s ease-in-out infinite" }} />
            )}
          </div>
        )}

        {/* Oval face guide */}
        <div
          className={`relative rounded-full border-[3px] overflow-hidden transition-all duration-500 ${ovalCls}`}
          style={{ width: "min(54vw, 220px)", height: "min(68vw, 275px)" }}
        >
          {/* Sweep beam inside oval when active */}
          {isActive && (
            <div
              className="absolute left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-blue-400 to-transparent opacity-90"
              style={{ animation: "scanBeam 1.8s ease-in-out infinite" }}
            />
          )}
          {/* Result icon inside oval */}
          {showResult && cfg && (
            <div className="absolute inset-0 flex items-center justify-center">
              {cfg.icon}
            </div>
          )}
        </div>

        {/* Progress bar below oval when scanning */}
        {isActive && (
          <div className="mt-4 w-36 sm:w-52 h-[3px] bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full w-2/5 bg-gradient-to-r from-transparent via-blue-400 to-transparent"
              style={{ animation: "progressBar 1.4s ease-in-out infinite" }}
            />
          </div>
        )}

        {/* Result text block */}
        {showResult && cfg && result && (
          <div className="mt-6 sm:mt-8 text-center max-w-xs sm:max-w-sm">
            <h2 className={`text-3xl sm:text-5xl font-extrabold ${cfg.textColor} leading-tight drop-shadow-lg`}>
              {result.student_name ?? cfg.title ?? "Lỗi"}
            </h2>
            {result.student_code && (
              <p className="text-white/50 text-lg sm:text-2xl font-mono mt-1">{result.student_code}</p>
            )}
            <p className="text-white/40 text-sm mt-2 leading-snug">{result.message}</p>
            {result.confidence > 0 && (() => {
                // buffalo_l cosine similarity for correct matches: ~0.75-0.95
                // Normalize [0.50, 1.0] → [85%, 100%] to reflect calibrated confidence
                // Scores below threshold show raw (for "unknown" status display)
                const MATCH_THRESHOLD = 0.50;
                const displayPct = result.confidence >= MATCH_THRESHOLD
                  ? Math.min(100, Math.round(85 + (result.confidence - MATCH_THRESHOLD) / (1 - MATCH_THRESHOLD) * 15))
                  : Math.round(result.confidence * 100);
                const barColor = displayPct >= 95 ? "bg-green-400" : displayPct >= 88 ? "bg-yellow-400" : "bg-red-400";
                return (
                  <div className="mt-4">
                    <div className="h-1.5 bg-white/10 rounded-full overflow-hidden w-32 sm:w-44 mx-auto">
                      <div className={`h-full rounded-full ${barColor}`} style={{ width: `${displayPct}%` }} />
                    </div>
                    <p className="text-white/25 text-xs mt-1">Confidence {displayPct}%</p>
                  </div>
                );
              })()}
          </div>
        )}
      </div>

      {/* ════════ BOTTOM BAR ═════════════════════════════════════════════ */}
      <div className="absolute bottom-0 left-0 right-0 z-20 flex flex-col items-center pb-8 sm:pb-10 px-6 gap-3">
        {!showResult && !isActive && (
          <p className="text-white/25 text-xs text-center">
            AIoT Smart Attendance · Look straight ahead, do not use photos
          </p>
        )}
        <button
          onClick={doScan}
          disabled={isActive || !camReady}
          className={`
            w-full max-w-xs sm:max-w-sm py-4 rounded-2xl font-bold text-base tracking-wide
            flex items-center justify-center gap-2.5 transition-all duration-200 active:scale-95 shadow-2xl
            ${isActive
              ? "bg-blue-700/55 text-blue-200 cursor-not-allowed border border-blue-500/30 backdrop-blur-sm"
              : "bg-blue-600 hover:bg-blue-500 text-white shadow-blue-900/50"}
          `}
        >
          {scanStatus === "scanning" ? (
            <><Loader2 className="w-5 h-5 animate-spin" /> Recognizing…</>
          ) : (
            <><Camera className="w-5 h-5" /> Scan Face</>
          )}
        </button>
      </div>

      {/* Hidden canvas for capture */}
      <canvas ref={canvasRef} className="hidden" aria-hidden="true" />
    </div>
  );
}

// ─────────────────────────── Page export ─────────────────────────────────────
export default function KioskPage() {
  const { classId } = useParams<{ classId: string }>();
  return (
    <Suspense fallback={
      <div className="fixed inset-0 bg-gray-950 flex items-center justify-center">
        <Loader2 className="w-10 h-10 text-blue-400 animate-spin" />
      </div>
    }>
      <KioskInner classId={classId} />
    </Suspense>
  );
}

