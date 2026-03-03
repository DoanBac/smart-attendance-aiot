"use client";
import { Users, Monitor, ClipboardCheck, WifiOff, Wifi } from "lucide-react";
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
  if (status === "present")       return "bg-green-100 text-green-700";
  if (status === "already_marked") return "bg-blue-100 text-blue-700";
  return "bg-gray-100 text-gray-600";
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
      const active  = Array.isArray(devices) ? devices.filter((d: { status: string }) => d.status === "active").length  : 0;
      const offline = Array.isArray(devices) ? devices.filter((d: { status: string }) => d.status !== "active").length  : 0;
      setStats({
        total_students:   Array.isArray(students) ? students.length : 0,
        active_devices:   active,
        offline_devices:  offline,
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
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">System Overview</h1>
          <p className="text-gray-500 mt-1">AIoT Smart Attendance — Real-time Dashboard</p>
        </div>
        <span className={`flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-full ${
          wsStatus === "connected"    ? "bg-green-100 text-green-700" :
          wsStatus === "connecting"   ? "bg-yellow-100 text-yellow-700" :
                                        "bg-red-100 text-red-600"
        }`}>
          {wsStatus === "connected" ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
          {wsStatus === "connected" ? "WebSocket Live" : wsStatus === "connecting" ? "Connecting…" : "Reconnecting…"}
        </span>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard icon={Users}          label="Total Students"      value={stats.total_students}   color="bg-blue-500" />
        <StatCard icon={Monitor}        label="Active Devices"      value={stats.active_devices}   color="bg-green-500" />
        <StatCard icon={ClipboardCheck} label="Today's Attendance"  value={stats.today_attendance} color="bg-purple-500" />
        <StatCard icon={WifiOff}        label="Offline Devices"     value={stats.offline_devices}  color="bg-red-500" />
      </div>

      {/* Realtime Feed */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          📡 Real-time Attendance Feed
        </h2>
        {feed.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <ClipboardCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No attendance events today.</p>
            <p className="text-sm mt-1">
              {wsStatus === "connected" ? "WebSocket connected — waiting for events…" : "Connecting to WebSocket…"}
            </p>
          </div>
        ) : (
          <div className="space-y-1 max-h-[480px] overflow-y-auto pr-1">
            {feed.map((item, i) => (
              <div key={item.id ?? i} className="flex items-center gap-3 py-2.5 px-3 rounded-lg hover:bg-gray-50 border-b border-gray-50 last:border-0">
                <div className="flex-1 min-w-0">
                  <span className="font-medium text-gray-800 truncate block">
                    {item.student_name ?? "Unknown"}
                  </span>
                  <span className="text-xs text-gray-400">Lớp #{item.class_id}</span>
                </div>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${statusBadge(item.status)}`}>
                  {item.status === "present" ? "Điểm danh" : item.status === "already_marked" ? "Đã có" : item.status}
                </span>
                <span className="text-sm bg-green-100 text-green-700 px-2 py-0.5 rounded-full font-mono">
                  {((item.confidence ?? 0) * 100).toFixed(1)}%
                </span>
                <span className="text-xs text-gray-400 whitespace-nowrap">
                  {new Date(item.timestamp).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
