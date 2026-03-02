"use client";
import { useState, useEffect } from "react";
import { BarChart2, Download } from "lucide-react";

interface AttendanceRecord {
  student_name: string | null;
  student_id: number;
  timestamp: string;
  status: string;
  confidence: number | null;
}

export default function ReportsPage() {
  const [classId, setClassId] = useState("1");
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  useEffect(() => {
    setLoading(true);
    fetch(`${base}/api/attendance/class/${classId}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json()).then(setRecords).catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, [classId]);

  // Aggregate stats
  const totalPresent = records.filter((r) => r.status === "present").length;
  const uniqueStudents = new Set(records.map((r) => r.student_id)).size;
  const avgConfidence = records.filter((r) => r.confidence).reduce((a, r) => a + (r.confidence ?? 0), 0) / (records.length || 1);

  const exportCSV = () => {
    const rows = [
      ["Timestamp", "Student ID", "Student Name", "Status", "Confidence"],
      ...records.map((r) => [
        new Date(r.timestamp).toLocaleString("en-US"),
        r.student_id,
        r.student_name || "",
        r.status,
        r.confidence?.toFixed(4) || "",
      ]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `attendance_class${classId}.csv`;
    a.click();
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Attendance Reports</h1>
        <div className="flex items-center gap-3">
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none"
          >
            {[1, 2, 3, 4, 5].map((id) => (
              <option key={id} value={id}>Class {id}</option>
            ))}
          </select>
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm hover:bg-gray-50"
          >
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">Total Records</p>
          <p className="text-3xl font-bold text-gray-800 mt-1">{records.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">Unique Students</p>
          <p className="text-3xl font-bold text-blue-600 mt-1">{uniqueStudents}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-500">Avg Confidence</p>
          <p className="text-3xl font-bold text-green-600 mt-1">
            {(avgConfidence * 100).toFixed(1)}%
          </p>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Timestamp</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Student</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Status</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Confidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {records.map((r, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-6 py-3 text-gray-500">{new Date(r.timestamp).toLocaleString("en-US")}</td>
                  <td className="px-6 py-3 font-medium text-gray-800">{r.student_name || `#${r.student_id}`}</td>
                  <td className="px-6 py-3">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${r.status === "present" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                      {r.status === "present" ? "Present" : "Absent"}
                    </span>
                  </td>
                  <td className="px-6 py-3 font-mono text-gray-600">
                    {r.confidence ? `${(r.confidence * 100).toFixed(1)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
