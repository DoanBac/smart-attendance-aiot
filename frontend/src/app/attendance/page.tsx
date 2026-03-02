"use client";
import { useEffect, useState, useRef } from "react";
import { getApiBase } from "@/lib/api";
import { RefreshCw, Wifi } from "lucide-react";

interface AttendanceRecord {
  id: number;
  student_id: number;
  student_name: string | null;
  class_id: number;
  timestamp: string;
  confidence: number | null;
  liveness_score: number | null;
  status: string;
  method: string;
}

export default function AttendancePage() {
  const [classId, setClassId] = useState("1");
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [wsStatus, setWsStatus] = useState<"connected" | "disconnected">("disconnected");
  const wsRef = useRef<WebSocket | null>(null);

  const base = getApiBase();
  const wsBase = base.replace("http", "ws");
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  const fetchRecords = () => {
    setLoading(true);
    fetch(`${base}/api/attendance/class/${classId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setRecords)
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  };

  // WebSocket for realtime updates
  useEffect(() => {
    const ws = new WebSocket(`${wsBase}/ws/attendance/${classId}`);
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.event === "attendance") {
          setRecords((prev) => [msg.data, ...prev]);
        }
      } catch {}
    };

    // Heartbeat
    const ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 30000);

    return () => {
      clearInterval(ping);
      ws.close();
    };
  }, [classId]);

  useEffect(() => {
    fetchRecords();
  }, [classId]);

  const confidenceColor = (score: number | null) => {
    if (!score) return "text-gray-400";
    if (score >= 0.85) return "text-green-600";
    if (score >= 0.70) return "text-yellow-600";
    return "text-red-600";
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Real-time Attendance</h1>
          <div className="flex items-center gap-2 mt-1">
            <Wifi className={`w-4 h-4 ${wsStatus === "connected" ? "text-green-500" : "text-gray-400"}`} />
            <span className="text-sm text-gray-500">
              {wsStatus === "connected" ? "WebSocket connected" : "WebSocket disconnected"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {[1, 2, 3, 4, 5].map((id) => (
              <option key={id} value={id}>Class {id}</option>
            ))}
          </select>
          <button
            onClick={fetchRecords}
            className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm hover:bg-gray-50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Timestamp</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Student</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Confidence</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Liveness</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Method</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {records.map((r) => (
                <tr key={r.id} className="hover:bg-gray-50">
                  <td className="px-6 py-3 text-gray-500">
                    {new Date(r.timestamp).toLocaleString("en-US")}
                  </td>
                  <td className="px-6 py-3 font-medium text-gray-800">
                    {r.student_name || `#${r.student_id}`}
                  </td>
                  <td className={`px-6 py-3 font-mono font-medium ${confidenceColor(r.confidence)}`}>
                    {r.confidence ? `${(r.confidence * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className={`px-6 py-3 font-mono ${confidenceColor(r.liveness_score)}`}>
                    {r.liveness_score ? `${(r.liveness_score * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="px-6 py-3">
                    <span className="bg-blue-100 text-blue-700 px-2 py-0.5 rounded text-xs">
                      {r.method}
                    </span>
                  </td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      r.status === "present" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                    }`}>
                      {r.status === "present" ? "Present" : "Absent"}
                    </span>
                  </td>
                </tr>
              ))}
              {records.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-gray-400">
                    No attendance records for this class today.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
