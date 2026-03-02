"use client";
import { useEffect, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Camera, CheckCircle, ArrowLeft, Wifi, Monitor } from "lucide-react";
import Link from "next/link";

const POSE_STEPS = [
  { label: "Look straight at the camera", emoji: "😐" },
  { label: "Turn head slightly left", emoji: "👈" },
  { label: "Turn head slightly right", emoji: "👉" },
  { label: "Tilt head slightly up", emoji: "☝️" },
  { label: "Tilt head slightly down", emoji: "👇" },
  { label: "Look straight (confirm)", emoji: "✅" },
];

// Minimum accepted frames required before moving to the next pose step.
// System will keep retrying until this many frames are accepted or
// MAX_ATTEMPTS_PER_STEP is reached.
const MIN_ACCEPTED_PER_STEP = 5;
// 60 attempts × 600 ms = 36 seconds per step before giving up.
// This is generous enough for any real-world lighting/positioning.
const MAX_ATTEMPTS_PER_STEP = 60;

type CameraMode = "local" | "ip";

function EnrollContent() {
  const searchParams = useSearchParams();
  const studentId = searchParams.get("student_id") || "";

  const videoRef = useRef<HTMLVideoElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [step, setStep] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const [capturing, setCapturing] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [inputId, setInputId] = useState(studentId);

  // Per-step acceptance tracking
  const [currentStepAccepted, setCurrentStepAccepted] = useState(0);
  const [stepAccepted, setStepAccepted] = useState<number[]>(new Array(POSE_STEPS.length).fill(0));
  // Last-frame rejection feedback
  const [rejectReason, setRejectReason] = useState<string | null>(null);
  // Live quality debug info (blur variance of last accepted frame)
  const [lastQuality, setLastQuality] = useState<{blur?: number; det?: number} | null>(null);
  // Current attempt counter for "still scanning" feedback
  const [currentAttempts, setCurrentAttempts] = useState(0);

  const [cameraMode, setCameraMode] = useState<CameraMode>("local");
  const [ipUrl, setIpUrl] = useState("http://192.168.123.234:8080");
  const [ipConnected, setIpConnected] = useState(false);
  const [ipConnecting, setIpConnecting] = useState(false);

  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  useEffect(() => {
    if (cameraMode === "local") {
      startLocalCamera();
    } else {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setIpConnected(false);
    }
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, [cameraMode]);

  const startLocalCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: "user" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      setError("");
    } catch {
      setError("Cannot access local camera. Please check browser permissions.");
    }
  };

  // Normalize base URL (strip trailing slash)
  const getBaseUrl = () => ipUrl.replace(/\/$/, "");

  const connectIpCamera = async () => {
    setIpConnected(false);
    setIpConnecting(true);
    setError("");

    const base = getBaseUrl();
    const shotUrl = `${base}/shot.jpg?t=${Date.now()}`;

    try {
      // Test connectivity bằng cách load 1 snapshot tĩnh (/shot.jpg)
      // Dùng Image() để tránh CORS/mixed-content của fetch
      await new Promise<void>((resolve, reject) => {
        const testImg = new Image();
        testImg.onload = () => resolve();
        testImg.onerror = () => reject(new Error("Cannot load snapshot"));
        testImg.src = shotUrl;
        setTimeout(() => reject(new Error("Timeout")), 5000);
      });

      // Nếu load được → hiện MJPEG stream trong <img> tag
      if (imgRef.current) {
        imgRef.current.src = `${base}/video?t=${Date.now()}`;
      }
      setIpConnected(true);
      setError("");
    } catch {
      setIpConnected(false);
      setError(
        `Cannot connect to IP Webcam at ${base}. ` +
        `Make sure: 1) Same WiFi network  2) URL is correct (try opening ${base} in browser first)  ` +
        `3) If using HTTPS, open ${base} in browser and accept the certificate first.`
      );
    } finally {
      setIpConnecting(false);
    }
  };

  // Capture frame: local = drawImage từ <video>, IP = fetch /shot.jpg
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
      // IP mode: fetch snapshot từ /shot.jpg
      try {
        const shotUrl = `${getBaseUrl()}/shot.jpg?t=${Date.now()}`;
        const res = await fetch(shotUrl);
        const blob = await res.blob();
        const bitmap = await createImageBitmap(blob);
        canvas.width = bitmap.width;
        canvas.height = bitmap.height;
        ctx.drawImage(bitmap, 0, 0);
        return canvas.toDataURL("image/jpeg", 0.85);
      } catch {
        return null;
      }
    }
  };

  const runEnrollment = async () => {
    if (!inputId) {
      setError("Please enter a Student ID.");
      return;
    }
    if (cameraMode === "ip" && !ipConnected) {
      setError("Please connect to the IP camera first.");
      return;
    }

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

        // Give the student 2 seconds to move into the correct pose
        await new Promise((r) => setTimeout(r, 2000));

        let accepted = 0;
        let attempts = 0;

        // Keep capturing until enough frames are accepted for this step.
        // The loop will NOT advance until MIN_ACCEPTED_PER_STEP good frames
        // are confirmed by the server — so wrong poses are naturally blocked.
        while (accepted < MIN_ACCEPTED_PER_STEP && attempts < MAX_ATTEMPTS_PER_STEP) {
          attempts++;
          setCurrentAttempts(attempts);
          // 600 ms between captures — longer than 400 ms prevents motion-blur
          // from the previous capture movement.
          await new Promise((r) => setTimeout(r, 600));

          const frame = await captureFrame();
          if (!frame) continue;

          try {
            const res = await fetch(`${base}/api/enrollment/capture-frame`, {
              method: "POST",
              headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                student_id: parseInt(inputId),
                frame_b64: frame.split(",")[1],
                step_index: s,
              }),
            });

            // Always try to parse JSON regardless of status code so we can
            // surface a proper reason instead of silently counting as rejected.
            let data: Record<string, unknown> = {};
            try {
              data = await res.json();
            } catch {
              // Binary/non-JSON response — treat as transient error, keep retrying
              setRejectReason("Server error — retrying…");
              continue;
            }

            if (data.accepted) {
              accepted++;
              setCurrentStepAccepted(accepted);
              setRejectReason(null);
              setLastQuality({
                blur: data.blur_variance as number | undefined,
                det: data.det_score as number | undefined,
              });
              setFrameCount((c) => c + 1);
              setStepAccepted((prev) => {
                const updated = [...prev];
                updated[s] = accepted;
                return updated;
              });
            } else {
              // Server rejected this frame — show reason so student can correct pose
              const reason = (data.reason as string) || "Frame not accepted";
              setRejectReason(reason);
            }
          } catch {
            // Network hiccup — keep retrying silently
          }
        }

        if (accepted < MIN_ACCEPTED_PER_STEP) {
          throw new Error(
            `Pose "${POSE_STEPS[s].label}": could not capture ${MIN_ACCEPTED_PER_STEP} valid frames ` +
            `after ${MAX_ATTEMPTS_PER_STEP} attempts. ` +
            `Please ensure good lighting and that your face is fully visible.`
          );
        }
      }

      // All steps satisfied — finalize
      setRejectReason(null);
      const res = await fetch(`${base}/api/enrollment/finalize`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ student_id: parseInt(inputId) }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Enrollment failed");
      }

      setDone(true);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "An error occurred");
    } finally {
      setCapturing(false);
    }
  };

  const progress = (step / POSE_STEPS.length) * 100;

  if (done) {
    return (
      <div className="p-8 max-w-xl mx-auto text-center">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-12">
          <CheckCircle className="w-20 h-20 text-green-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-800 mb-2">Enrollment Successful!</h2>
          <p className="text-gray-500 mb-6">
            Face for student #{inputId} has been registered with {frameCount} frames.
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
      <p className="text-gray-500 mb-6 text-sm">3D-like Face Scan  6 angles</p>

      {/* Camera source selector */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setCameraMode("local")}
          disabled={capturing}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
            cameraMode === "local"
              ? "bg-blue-600 text-white border-blue-600"
              : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
          } disabled:opacity-50`}
        >
          <Monitor className="w-4 h-4" /> Local Webcam
        </button>
        <button
          onClick={() => setCameraMode("ip")}
          disabled={capturing}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
            cameraMode === "ip"
              ? "bg-blue-600 text-white border-blue-600"
              : "bg-white text-gray-600 border-gray-200 hover:bg-gray-50"
          } disabled:opacity-50`}
        >
          <Wifi className="w-4 h-4" /> IP Webcam
        </button>
      </div>

      {/* IP Camera URL input */}
      {cameraMode === "ip" && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-6">
          <p className="text-sm font-medium text-blue-800 mb-1">IP Webcam URL</p>
          <p className="text-xs text-blue-600 mb-3">
            Open <strong>IP Webcam</strong> app on your phone  tap <strong>Start server</strong>  enter the address shown (e.g.{" "}
            <code className="bg-blue-100 px-1 rounded">http://192.168.x.x:8080</code>)
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              value={ipUrl}
              onChange={(e) => setIpUrl(e.target.value)}
              disabled={capturing}
              placeholder="http://192.168.1.100:8080"
              className="flex-1 px-3 py-2 border border-blue-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white disabled:opacity-60"
            />
            <button
              onClick={connectIpCamera}
              disabled={capturing || ipConnecting}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
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
          {/* Local cam: video element | IP cam: img element (MJPEG renders correctly in <img>) */}
          {cameraMode === "ip" ? (
            <img
              ref={imgRef}
              alt="IP Camera stream"
              className="w-full h-full object-cover"
            />
          ) : (
            <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
          )}
          <canvas ref={canvasRef} className="hidden" />

          {/* Overlay guide circle — turns red when last frame was rejected */}
          {capturing && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div
                className={`border-4 rounded-full w-48 h-48 opacity-60 animate-pulse ${
                  rejectReason ? "border-red-400" : "border-blue-400"
                }`}
              />
            </div>
          )}

          {/* Rejection banner — tells student exactly what's wrong */}
          {capturing && rejectReason && (
            <div className="absolute top-4 left-0 right-0 flex justify-center pointer-events-none">
              <span className="bg-red-600/90 text-white px-4 py-2 rounded-full text-sm font-medium max-w-xs text-center">
                ⚠️ {rejectReason}
              </span>
            </div>
          )}

          {/* Scanning indicator — shown when no rejection but also no acceptance yet */}
          {capturing && !rejectReason && currentStepAccepted === 0 && currentAttempts > 0 && (
            <div className="absolute top-4 left-0 right-0 flex justify-center pointer-events-none">
              <span className="bg-yellow-500/90 text-white px-4 py-2 rounded-full text-sm font-medium">
                🔍 Scanning… ({currentAttempts}/{MAX_ATTEMPTS_PER_STEP})
              </span>
            </div>
          )}

          {/* Step label + per-step progress on video */}
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

          {/* IP mode badge */}
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
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Student ID</label>
            <input
              type="number"
              value={inputId}
              onChange={(e) => setInputId(e.target.value)}
              disabled={capturing}
              className="w-full px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60"
              placeholder="Enter student ID from the system..."
            />
          </div>

          <div>
            <div className="flex justify-between text-sm text-gray-500 mb-2">
              <span>Progress</span>
              <span>{step}/{POSE_STEPS.length} steps</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2 mb-4">
              <div
                className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                style={{ width: `${capturing ? progress : 0}%` }}
              />
            </div>
            <div className="space-y-2">
              {POSE_STEPS.map((ps, i) => (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                    capturing && i === step
                      ? "bg-blue-50 border border-blue-200 text-blue-700"
                      : capturing && i < step
                      ? "text-green-600"
                      : "text-gray-400"
                  }`}
                >
                  <span className="text-lg">{ps.emoji}</span>
                  <span className="flex-1">{ps.label}</span>

                  {/* Completed step: show tick + count */}
                  {capturing && i < step && (
                    <span className="flex items-center gap-1 text-xs text-green-600 font-medium">
                      <CheckCircle className="w-4 h-4" />
                      {stepAccepted[i]}/{MIN_ACCEPTED_PER_STEP}
                    </span>
                  )}

                  {/* Active step: show live accepted/total */}
                  {capturing && i === step && (
                    <span className={`text-xs font-bold ${
                      rejectReason ? "text-red-500" : "text-blue-600"
                    }`}>
                      {currentStepAccepted}/{MIN_ACCEPTED_PER_STEP}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>

          {capturing && (
            <div className="text-center text-sm text-gray-500">
              Collected{" "}
              <span className="font-bold text-blue-600">{frameCount}</span> high-quality frames
              {lastQuality?.blur !== undefined && (
                <span className="ml-2 text-xs text-gray-400">
                  (blur: {lastQuality.blur.toFixed(0)}
                  {lastQuality.det !== undefined && `, det: ${lastQuality.det.toFixed(2)}`})
                </span>
              )}
            </div>
          )}

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <button
            onClick={runEnrollment}
            disabled={capturing || (cameraMode === "ip" && !ipConnected)}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white py-3 rounded-xl font-medium hover:bg-blue-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {capturing ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                Capturing face data...
              </>
            ) : (
              <>
                <Camera className="w-5 h-5" />
                Start Face Enrollment
              </>
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
