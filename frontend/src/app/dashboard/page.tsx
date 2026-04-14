"use client";
import { Users, Monitor, ClipboardCheck, WifiOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getApiBase, getWsBase } from "@/lib/api";

interface Stats {
  total_students: number;
  active_devices: number;
  today_attendance: number;
  offline_devices: number;
}

interface FeedItem {
  id: number;
  student_name: string | null;
  class_id: number;
  class_name: string | null;
  class_code: string | null;
  timestamp: string;
  confidence: number;
  status: string;
}

function StatCard({
  icon: Icon, label, value, color,
}: {
  icon: React.ElementType; label: string; value: number | string; color: string;
}) {
  return (
    <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">{value}</p>
        </div>
        <div className={`p-3 rounded-full ${color}`}>
          <Icon className="w-6 h-6 text-white" />
        </div>
      </div>
    </div>
  );
}

function statusBadge(status: string) {
  if (status === "present")        return "bg-green-100 text-green-700";
  if (status === "already_marked") return "bg-blue-100 text-blue-700";
  if (status === "wrong_class")    return "bg-purple-100 text-purple-700";
  return "bg-gray-100 text-gray-600";
}

function statusLabel(status: string) {
  if (status === "present")        return "Present";
  if (status === "already_marked") return "Already in";
  if (status === "wrong_class")    return "Wrong class";
  if (status === "unknown")        return "Unknown";
  if (status === "no_face")        return "No face";
  if (status === "liveness_failed") return "Liveness fail";
  return status;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({
    total_students: 0,
    active_devices: 0,
    today_attendance: 0,
    offline_devices: 0,
  });
  const [loading, setLoading] = useState(true);
  const [feed, setFeed]       = useState<FeedItem[]>([]);
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    const base  = getApiBase();

    // Fetch stats in parallel
    Promise.all([
      fetch(`${base}/api/students/`,  { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/devices/`,   { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/attendance/today`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json()).catch(() => []),
    ]).then(([students, devices, today]) => {
      // A device is "online" only if status=active AND heartbeat within 10 min
      const TEN_MIN = 10 * 60 * 1000;
      const now = Date.now();
      const activeDevices = Array.isArray(devices)
        ? devices.filter((d: { status: string; last_heartbeat: string | null }) => {
            if (d.status !== "active") return false;
            if (!d.last_heartbeat) return false;
            return now - new Date(d.last_heartbeat).getTime() < TEN_MIN;
          })
        : [];
      const offlineDevices = Array.isArray(devices)
        ? devices.filter((d: { status: string; last_heartbeat: string | null }) => {
            if (d.status !== "active") return false; // skip intentionally inactive
            if (!d.last_heartbeat) return true;       // never sent heartbeat = offline
            return now - new Date(d.last_heartbeat).getTime() >= TEN_MIN;
          })
        : [];
      setStats({
        total_students:   Array.isArray(students) ? students.length : 0,
        active_devices:   activeDevices.length,
        offline_devices:  offlineDevices.length,
        today_attendance: Array.isArray(today)    ? today.length    : 0,
      });
      if (Array.isArray(today)) {
        setFeed(today.map((r: FeedItem) => ({ ...r })));
      }
    }).finally(() => setLoading(false));

    // WebSocket — global dashboard channel
    const wsBase = getWsBase();
    const connect = () => {
      const ws = new WebSocket(`${wsBase}/ws/attendance/all`);
      wsRef.current = ws;
      ws.onopen  = () => setWsStatus("connected");
      ws.onclose = () => { setWsStatus("disconnected"); setTimeout(connect, 3000); };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.event === "attendance" && msg.data) {
            const r: FeedItem = msg.data;
            setFeed(prev => [r, ...prev.slice(0, 99)]);
            setStats(s => ({ ...s, today_attendance: s.today_attendance + 1 }));
          }
        } catch (_e) { /* ignore */ }
      };
    };
    connect();

    return () => { wsRef.current?.close(); };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-800">System Overview</h1>
        <p className="text-gray-500 mt-1">AIoT Smart Attendance — Real-time Dashboard</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard icon={Users}          label="Total Students"      value={stats.total_students}   color="bg-blue-500" />
        <StatCard icon={Monitor}        label="Active Devices"      value={stats.active_devices}   color="bg-green-500" />
        <StatCard icon={ClipboardCheck} label="Today's Attendance"  value={stats.today_attendance} color="bg-purple-500" />
        <StatCard icon={WifiOff}        label="Offline Devices"     value={stats.offline_devices}  color="bg-red-500" />
      </div>

      {/* Realtime Feed */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {/* Table header bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 bg-blue-50 rounded-lg">
              <ClipboardCheck className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-gray-800">Real-time Attendance Feed</h2>
              <p className="text-xs text-gray-400 mt-0.5">Today — {new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400 bg-gray-50 px-2.5 py-1 rounded-full border border-gray-100">
              {feed.length} event{feed.length !== 1 ? "s" : ""}
            </span>
            <span className={`flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full border ${
              wsStatus === "connected"  ? "bg-green-50 text-green-700 border-green-100" :
              wsStatus === "connecting" ? "bg-yellow-50 text-yellow-700 border-yellow-100" :
                                          "bg-red-50 text-red-600 border-red-100"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${wsStatus === "connected" ? "bg-green-500 animate-pulse" : wsStatus === "connecting" ? "bg-yellow-500" : "bg-red-500"}`} />
              {wsStatus === "connected" ? "Live" : wsStatus === "connecting" ? "Connecting…" : "Reconnecting…"}
            </span>
          </div>
        </div>

        {feed.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <ClipboardCheck className="w-12 h-12 mx-auto mb-3 opacity-20" />
            <p className="font-medium">No attendance events today.</p>
            <p className="text-sm mt-1 text-gray-300">
              {wsStatus === "connected" ? "WebSocket connected — waiting for events…" : "Connecting to WebSocket…"}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-8">#</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Student</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Class</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="text-center px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Confidence</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50 max-h-[480px]">
                {feed.map((item, i) => (
                  <tr key={item.id ?? i} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-6 py-3.5 text-xs text-gray-300 font-mono">{i + 1}</td>
                    <td className="px-4 py-3.5">
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-400 to-indigo-500 flex items-center justify-center text-white text-xs font-bold shrink-0">
                          {(item.student_name ?? "?")[0].toUpperCase()}
                        </div>
                        <span className="font-medium text-gray-800 truncate max-w-[160px]">
                          {item.student_name ?? <span className="text-gray-400 italic">Unknown</span>}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3.5">
                      <div>
                        <span className="text-gray-700 font-medium">
                          {item.class_name ?? `Class #${item.class_id}`}
                        </span>
                        {item.class_code && (
                          <span className="ml-1.5 text-xs text-gray-400 font-mono bg-gray-100 px-1.5 py-0.5 rounded">
                            {item.class_code}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <span className={`inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full ${statusBadge(item.status)}`}>
                        <span className="w-1.5 h-1.5 rounded-full bg-current opacity-70" />
                        {statusLabel(item.status)}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${
                        (item.confidence ?? 0) >= 0.85 ? "text-green-700 bg-green-50" :
                        (item.confidence ?? 0) >= 0.70 ? "text-yellow-700 bg-yellow-50" :
                                                          "text-red-700 bg-red-50"
                      }`}>
                        {((item.confidence ?? 0) * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="px-6 py-3.5 text-right text-xs text-gray-400 whitespace-nowrap font-mono">
                      {new Date(item.timestamp).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  );
}
