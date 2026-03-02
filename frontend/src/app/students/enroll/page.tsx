"use client";
import { useEffect, useRef, useState, Suspense } from "react";
import { getApiBase } from "@/lib/api";
import { useSearchParams } from "next/navigation";
import { Camera, CheckCircle, ArrowLeft, Wifi, Monitor, Search, X } from "lucide-react";
import Link from "next/link";

const POSE_STEPS = [
  { label: "Look straight at the camera", emoji: "😐" },
  { label: "Turn head slightly left", emoji: "👈" },
  { label: "Turn head slightly right", emoji: "👉" },
  { label: "Tilt head slightly up", emoji: "☝️" },
  { label: "Tilt head slightly down", emoji: "👇" },
  { label: "Look straight (confirm)", emoji: "✅" },
];

const MIN_ACCEPTED_PER_STEP = 5;
const MAX_ATTEMPTS_PER_STEP = 60;

type CameraMode = "local" | "ip";

interface Student {
  id: number;
  student_code: string;
  full_name: string;
  status: string;
  has_face: boolean;
}

function EnrollContent() {
  const searchParams = useSearchParams();
  const preselectedId = searchParams.get("student_id") || ""; // numeric DB id from URL

  const videoRef = useRef<HTMLVideoElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [step, setStep] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const [capturing, setCapturing] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  // ── Student picker ───────────────────────────────────────────────────────
  const [students, setStudents] = useState<Student[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<Student | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [showDropdown, setShowDropdown] = useState(false);

  // Per-step acceptance tracking
  const [currentStepAccepted, setCurrentStepAccepted] = useState(0);
  const [stepAccepted, setStepAccepted] = useState<number[]>(new Array(POSE_STEPS.length).fill(0));
  const [rejectReason, setRejectReason] = useState<string | null>(null);
  const [lastQuality, setLastQuality] = useState<{blur?: number; det?: number; yaw?: number; pitch?: number} | null>(null);
  const [currentAttempts, setCurrentAttempts] = useState(0);

  const [cameraMode, setCameraMode] = useState<CameraMode>("local");
  const [ipUrl, setIpUrl] = useState("http://192.168.123.234:8080");
  const [ipConnected, setIpConnected] = useState(false);
  const [ipConnecting, setIpConnecting] = useState(false);

  const base = getApiBase();
  const getToken = () => (typeof window !== "undefined" ? localStorage.getItem("access_token") ?? "" : "");

  // ── Fetch all active students on mount ───────────────────────────────────
  useEffect(() => {
    fetch(`${base}/api/students/?include_inactive=false`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => r.json())
      .then((data) => {
        const list: Student[] = Array.isArray(data) ? data : (data.items ?? []);
        setStudents(list);
        // Auto-select if student_id was passed in URL
        if (preselectedId) {
          const found = list.find((s) => s.id === parseInt(preselectedId));
          if (found) {
            setSelectedStudent(found);
            setSearchQuery(`${found.student_code} — ${found.full_name}`);
          }
        }
      })
      .catch(() => {});
  }, [base, preselectedId]);

  // ── Camera setup ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (cameraMode === "local") {
      startLocalCamera();
    } else {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setIpConnected(false);
    }
    return () => { streamRef.current?.getTracks().forEach((t) => t.stop()); };
  }, [cameraMode]);

  const startLocalCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
      });
      streamRef.current = stream;
      if (videoRef.current) videoRef.current.srcObject = stream;
      setError("");
    } catch {
      setError("Cannot access local camera. Please check browser permissions.");
    }
  };

  const getBaseUrl = () => ipUrl.replace(/\/$/, "");

  const connectIpCamera = async () => {
    setIpConnected(false);
    setIpConnecting(true);
    setError("");
    const bUrl = getBaseUrl();
    try {
      await new Promise<void>((resolve, reject) => {
        const testImg = new Image();
        testImg.onload = () => resolve();
        testImg.onerror = () => reject(new Error("Cannot load snapshot"));
        testImg.src = `${bUrl}/shot.jpg?t=${Date.now()}`;
        setTimeout(() => reject(new Error("Timeout")), 5000);
      });
      if (imgRef.current) imgRef.current.src = `${bUrl}/video?t=${Date.now()}`;
      setIpConnected(true);
      setError("");
    } catch {
      setIpConnected(false);
      setError(
        `Cannot connect to IP Webcam at ${bUrl}. ` +
        `Make sure: 1) Same WiFi network  2) URL is correct  3) Accept cert in browser first.`
      );
    } finally {
      setIpConnecting(false);
    }
  };

  const captureFrame = async (): Promise<string | null> => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    if (cameraMode === "local") {
      const video = videoRef.current;
      if (!video) return null;
      canvas.width = video.videoWidth || 640;
      canvas.height = video.videoHeight || 480;
      ctx.drawImage(video, 0, 0);
      return canvas.toDataURL("image/jpeg", 0.85);
    } else {
      try {
        const res = await fetch(`${getBaseUrl()}/shot.jpg?t=${Date.now()}`);
        const bitmap = await createImageBitmap(await res.blob());
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        ctx.drawImage(bitmap, 0, 0);
        return canvas.toDataURL("image/jpeg", 0.85);
      } catch { return null; }
    }
  };

  const runEnrollment = async () => {
    if (!selectedStudent) { setError("Please select a student first."); return; }
    if (cameraMode === "ip" && !ipConnected) { setError("Please connect to the IP camera first."); return; }

    setCapturing(true);
    setError("");
    setFrameCount(0);
    setCurrentStepAccepted(0);
    setRejectReason(null);
    setLastQuality(null);
    setCurrentAttempts(0);
    setStepAccepted(new Array(POSE_STEPS.length).fill(0));

    try {
      for (let s = 0; s < POSE_STEPS.length; s++) {
        setStep(s);
        setCurrentStepAccepted(0);
        setCurrentAttempts(0);
        setRejectReason(null);

        await new Promise((r) => setTimeout(r, 2000));

        let accepted = 0;
        let attempts = 0;

        while (accepted < MIN_ACCEPTED_PER_STEP && attempts < MAX_ATTEMPTS_PER_STEP) {
          attempts++;
          setCurrentAttempts(attempts);
          await new Promise((r) => setTimeout(r, 600));

          const frame = await captureFrame();
          if (!frame) continue;

          try {
            const res = await fetch(`${base}/api/enrollment/capture-frame`, {
              method: "POST",
              headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
              body: JSON.stringify({
                student_id: selectedStudent.id,
                frame_b64: frame.split(",")[1],
                step_index: s,
              }),
            });

            if (res.status === 401) throw new Error("Session expired. Please log out and log in again, then retry enrollment.");

            let data: Record<string, unknown> = {};
            try { data = await res.json(); } catch { setRejectReason("Server error — retrying…"); continue; }

            if (data.accepted) {
              accepted++;
              setCurrentStepAccepted(accepted);
              setRejectReason(null);
              setLastQuality({
                blur: data.blur_variance as number | undefined,
                det: data.det_score as number | undefined,
                yaw: data.yaw as number | undefined,
                pitch: data.pitch as number | undefined,
              });
              setFrameCount((c) => c + 1);
              setStepAccepted((prev) => { const u = [...prev]; u[s] = accepted; return u; });
            } else {
              setRejectReason((data.reason as string) || "Frame not accepted");
            }
          } catch (e: unknown) {
            if (e instanceof Error && e.message.includes("Session expired")) throw e;
          }
        }

        if (accepted < MIN_ACCEPTED_PER_STEP) {
          throw new Error(
            `Pose "${POSE_STEPS[s].label}": could not capture ${MIN_ACCEPTED_PER_STEP} valid frames ` +
            `after ${MAX_ATTEMPTS_PER_STEP} attempts. Please ensure good lighting and face fully visible.`
          );
        }
      }

      setRejectReason(null);
      const res = await fetch(`${base}/api/enrollment/finalize`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
        body: JSON.stringify({ student_id: selectedStudent.id }),
      });

      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Enrollment failed"); }
      setDone(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setCapturing(false);
    }
  };

  // ── Filtered student list for dropdown ───────────────────────────────────
  const filteredStudents = students.filter((s) => {
    const q = searchQuery.toLowerCase();
    return (
      s.student_code.toLowerCase().includes(q) ||
      s.full_name.toLowerCase().includes(q)
    );
  });

  const progress = (step / POSE_STEPS.length) * 100;

  if (done) {
    return (
      <div className="p-8 max-w-xl mx-auto text-center">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12">
          <CheckCircle className="w-20 h-20 text-green-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Enrollment Successful!</h2>
          <p className="text-gray-500 mb-6">
            Face for <span className="font-semibold text-gray-700">{selectedStudent?.student_code} — {selectedStudent?.full_name}</span> registered with {frameCount} frames.
          </p>
          <Link href="/students" className="bg-blue-600 text-white px-6 py-2.5 rounded-lg hover:bg-blue-700 transition-colors inline-block">
            Back to student list
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <Link href="/students" className="flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 text-sm">
        <ArrowLeft className="w-4 h-4" /> Back
      </Link>

      <h1 className="text-2xl font-bold text-gray-800 mb-2">Face Enrollment</h1>
      <p className="text-gray-500 mb-6 text-sm">3D-like Face Scan — 6 angles</p>

      {/* Camera mode selector */}
      <div className="flex gap-2 mb-6">
        <button onClick={() => setCameraMode("local")} disabled={capturing}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${cameraMode === "local" ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"} disabled:opacity-50`}>
          <Monitor className="w-4 h-4" /> Local Webcam
        </button>
        <button onClick={() => setCameraMode("ip")} disabled={capturing}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${cameraMode === "ip" ? "bg-blue-600 text-white border-blue-600" : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"} disabled:opacity-50`}>
          <Wifi className="w-4 h-4" /> IP Webcam
        </button>
      </div>

      {/* IP Camera URL input */}
      {cameraMode === "ip" && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
          <p className="text-sm font-medium text-blue-800 mb-1">IP Webcam URL</p>
          <p className="text-xs text-blue-600 mb-3">
            Open <strong>IP Webcam</strong> app on your phone → tap <strong>Start server</strong> → enter the address shown (e.g.{" "}
            <code className="bg-blue-100 px-1 rounded">http://192.168.x.x:8080</code>)
          </p>
          <div className="flex gap-2">
            <input type="text" value={ipUrl} onChange={(e) => setIpUrl(e.target.value)} disabled={capturing}
              placeholder="http://192.168.1.100:8080"
              className="flex-1 px-3 py-2 border border-blue-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white disabled:opacity-60" />
            <button onClick={connectIpCamera} disabled={capturing || ipConnecting}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50">
              {ipConnecting ? "Connecting..." : "Connect"}
            </button>
          </div>
          {ipConnected && (
            <p className="text-xs text-green-600 mt-2 flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> Connected to IP camera
            </p>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Camera preview */}
        <div className="bg-black rounded-2xl overflow-hidden aspect-video relative">
          {cameraMode === "ip" ? (
            <img ref={imgRef} alt="IP Camera stream" className="w-full h-full object-cover" />
          ) : (
            <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" style={{ transform: "scaleX(-1)" }} />
          )}
          <canvas ref={canvasRef} className="hidden" />

          {capturing && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className={`border-4 rounded-full w-48 h-48 opacity-60 animate-pulse ${rejectReason ? "border-red-400" : "border-blue-400"}`} />
            </div>
          )}

          {capturing && rejectReason && (
            <div className="absolute top-4 left-0 right-0 flex justify-center pointer-events-none">
              <span className="bg-red-600/90 text-white px-4 py-2 rounded-full text-sm font-medium max-w-xs text-center">
                ⚠️ {rejectReason}
              </span>
            </div>
          )}

          {capturing && !rejectReason && currentStepAccepted === 0 && currentAttempts > 0 && (
            <div className="absolute top-4 left-0 right-0 flex justify-center pointer-events-none">
              <span className="bg-yellow-500/90 text-white px-4 py-2 rounded-full text-sm font-medium">
                🔍 Scanning… ({currentAttempts}/{MAX_ATTEMPTS_PER_STEP})
              </span>
            </div>
          )}

          {capturing && (
            <div className="absolute bottom-4 left-0 right-0 text-center space-y-1">
              <div>
                <span className="bg-black/70 text-white px-4 py-2 rounded-full text-sm">
                  {POSE_STEPS[step]?.emoji} {POSE_STEPS[step]?.label}
                </span>
              </div>
              <div>
                <span className="bg-black/50 text-white px-3 py-1 rounded-full text-xs">
                  {currentStepAccepted} / {MIN_ACCEPTED_PER_STEP} frames accepted
                </span>
              </div>
            </div>
          )}

          {cameraMode === "ip" && (
            <div className="absolute top-3 left-3">
              <span className={`flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${ipConnected ? "bg-green-500/80 text-white" : "bg-yellow-500/80 text-white"}`}>
                <Wifi className="w-3 h-3" />
                {ipConnected ? "IP Camera" : "Not connected"}
              </span>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="space-y-6">

          {/* ── Student picker ─────────────────────────────────────────────── */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Student</label>

            {selectedStudent ? (
              /* Selected state — show chip with clear button */
              <div className="flex items-center gap-3 px-4 py-3 border border-blue-300 bg-blue-50 rounded-lg">
                <div className="flex-1 min-w-0">
                  <p className="font-mono font-semibold text-blue-700 text-sm">{selectedStudent.student_code}</p>
                  <p className="text-gray-700 text-sm truncate">{selectedStudent.full_name}</p>
                  {selectedStudent.has_face && (
                    <p className="text-xs text-orange-500 mt-0.5">⚠️ Already has face data — will be overwritten</p>
                  )}
                </div>
                {!capturing && (
                  <button
                    onClick={() => { setSelectedStudent(null); setSearchQuery(""); }}
                    className="flex-shrink-0 text-gray-400 hover:text-gray-600 p-1"
                    title="Change student"
                  >
                    <X className="w-4 h-4" />
                  </button>
                )}
              </div>
            ) : (
              /* Search / select state */
              <div className="relative">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => { setSearchQuery(e.target.value); setShowDropdown(true); }}
                    onFocus={() => setShowDropdown(true)}
                    onBlur={() => setTimeout(() => setShowDropdown(false), 150)}
                    disabled={capturing}
                    placeholder="Search by name or student code (FSB001)…"
                    className="w-full pl-9 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
                  />
                </div>

                {showDropdown && filteredStudents.length > 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-56 overflow-y-auto">
                    {filteredStudents.map((s) => (
                      <button
                        key={s.id}
                        onMouseDown={() => {
                          setSelectedStudent(s);
                          setSearchQuery(`${s.student_code} — ${s.full_name}`);
                          setShowDropdown(false);
                        }}
                        className="w-full text-left px-4 py-2.5 hover:bg-blue-50 border-b border-gray-50 last:border-0 transition-colors"
                      >
                        <span className="font-mono text-xs font-semibold text-blue-600 mr-2">{s.student_code}</span>
                        <span className="text-sm text-gray-700">{s.full_name}</span>
                        {s.has_face && (
                          <span className="ml-2 text-xs text-orange-500">★ has face</span>
                        )}
                      </button>
                    ))}
                  </div>
                )}

                {showDropdown && searchQuery && filteredStudents.length === 0 && (
                  <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg px-4 py-3 text-sm text-gray-400">
                    No students found for "{searchQuery}"
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Progress steps */}
          <div>
            <div className="flex justify-between text-sm text-gray-500 mb-2">
              <span>Progress</span>
              <span>{step}/{POSE_STEPS.length} steps</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 mb-4">
              <div className="bg-blue-600 h-2 rounded-full transition-all duration-500" style={{ width: `${capturing ? progress : 0}%` }} />
            </div>
            <div className="space-y-2">
              {POSE_STEPS.map((ps, i) => (
                <div key={i} className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                  capturing && i === step ? "bg-blue-50 border border-blue-200 text-blue-700"
                  : capturing && i < step ? "text-green-600" : "text-gray-400"}`}>
                  <span className="text-lg">{ps.emoji}</span>
                  <span className="flex-1">{ps.label}</span>
                  {capturing && i < step && (
                    <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                      <CheckCircle className="w-4 h-4" />{stepAccepted[i]}/{MIN_ACCEPTED_PER_STEP}
                    </span>
                  )}
                  {capturing && i === step && (
                    <span className={`text-xs font-bold ${rejectReason ? "text-red-500" : "text-blue-600"}`}>
                      {currentStepAccepted}/{MIN_ACCEPTED_PER_STEP}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {capturing && (
            <div className="text-center text-sm text-gray-500">
              Collected <span className="font-bold text-blue-600">{frameCount}</span> high-quality frames
              {lastQuality?.blur !== undefined && (
                <span className="ml-2 text-xs text-gray-400">
                  (blur: {lastQuality.blur.toFixed(0)}
                  {lastQuality.det !== undefined && `, det: ${lastQuality.det.toFixed(2)}`}
                  {lastQuality.yaw !== undefined && `, yaw: ${lastQuality.yaw.toFixed(1)}°`}
                  {lastQuality.pitch !== undefined && `, pitch: ${lastQuality.pitch.toFixed(1)}°`})
                </span>
              )}
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">{error}</div>
          )}

          <button
            onClick={runEnrollment}
            disabled={capturing || !selectedStudent || (cameraMode === "ip" && !ipConnected)}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white py-3 rounded-xl font-medium hover:bg-blue-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {capturing ? (
              <><div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" /> Capturing face data...</>
            ) : (
              <><Camera className="w-5 h-5" /> Start Face Enrollment</>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function EnrollPage() {
  return (
    <Suspense fallback={<div className="p-8">Loading...</div>}>
      <EnrollContent />
    </Suspense>
  );
}

