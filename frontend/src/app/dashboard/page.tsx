"use client";
import { Users, Monitor, ClipboardCheck, WifiOff } from "lucide-react";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";

interface Stats {
  total_students: number;
  active_devices: number;
  today_attendance: number;
  offline_devices: number;
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

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats>({
    total_students: 0,
    active_devices: 0,
    today_attendance: 0,
    offline_devices: 0,
  });
  const [loading, setLoading] = useState(true);
  const [realtimeFeed, setRealtimeFeed] = useState<{ name: string; time: string; score: number }[]>([]);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    const base = getApiBase();

    // Fetch students count
    fetch(`${base}/api/students/`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data: unknown[]) =>
        setStats((s) => ({ ...s, total_students: data.length }))
      )
      .catch(() => {});

    // Fetch devices count
    fetch(`${base}/api/devices/`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then((data: { status: string }[]) => {
        const active = data.filter((d) => d.status === "active").length;
        const offline = data.filter((d) => d.status !== "active").length;
        setStats((s) => ({ ...s, active_devices: active, offline_devices: offline }));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
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

      {/* Realtime Feed placeholder */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          📡 Real-time Attendance Feed
        </h2>
        {realtimeFeed.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <ClipboardCheck className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No attendance events today.</p>
            <p className="text-sm mt-1">WebSocket is waiting for events from Edge device...</p>
          </div>
        ) : (
          <div className="space-y-3">
            {realtimeFeed.map((item, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-gray-50">
                <span className="font-medium text-gray-700">{item.name}</span>
                <span className="text-sm text-gray-400">{item.time}</span>
                <span className="text-sm bg-green-100 text-green-700 px-2 py-0.5 rounded">
                  {(item.score * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
