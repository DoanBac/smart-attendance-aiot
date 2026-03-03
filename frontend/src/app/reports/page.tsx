"use client";
import { useState, useEffect, useCallback } from "react";
import { getApiBase } from "@/lib/api";
import { Download, FileText, Users, CheckCircle2, CalendarDays, FileSpreadsheet, UserX } from "lucide-react";

interface AttendanceRecord {
  student_name: string | null;
  student_id: number;
  timestamp: string;
  status: string;
  confidence: number | null;
  method: string | null;
}

interface AbsentStudent {
  student_id: number;
  student_code: string;
  student_name: string;
  email: string;
}

interface ClassOption {
  id: number;
  class_name: string;
}

export default function ReportsPage() {
  const [classes, setClasses] = useState<ClassOption[]>([]);
  const [classId, setClassId] = useState<string>("");
  const [date, setDate] = useState<string>(new Date().toISOString().slice(0, 10)); // YYYY-MM-DD
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [absentStudents, setAbsentStudents] = useState<AbsentStudent[]>([]);
  const [loading, setLoading] = useState(false);
  const [classesLoading, setClassesLoading] = useState(true);
  const [showAbsent, setShowAbsent] = useState(false);
  const [exportingXlsx, setExportingXlsx] = useState(false);

  const base = getApiBase();
  const getToken = () =>
    typeof window !== "undefined" ? localStorage.getItem("access_token") ?? "" : "";

  // ── Load classes from API ─────────────────────────────────────────────────
  useEffect(() => {
    setClassesLoading(true);
    fetch(`${base}/api/classes/`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((data) => {
        const list: ClassOption[] = Array.isArray(data) ? data : (data.items ?? []);
        setClasses(list);
        if (list.length > 0 && !classId) setClassId(String(list[0].id));
      })
      .catch(() => setClasses([]))
      .finally(() => setClassesLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [base]);

  // ── Fetch attendance records + absent list ────────────────────────────────
  const fetchRecords = useCallback(() => {
    if (!classId) return;
    setLoading(true);
    const dateParam = date ? `?date=${encodeURIComponent(date + "T00:00:00")}` : "";
    const headers = { Authorization: `Bearer ${getToken()}` };

    Promise.all([
      fetch(`${base}/api/attendance/class/${classId}${dateParam}`, { headers }).then((r) => r.json()),
      fetch(`${base}/api/attendance/class/${classId}/absent${dateParam}`, { headers }).then((r) => r.json()),
    ])
      .then(([present, absent]) => {
        setRecords(Array.isArray(present) ? present : []);
        setAbsentStudents(Array.isArray(absent) ? absent : []);
      })
      .catch(() => { setRecords([]); setAbsentStudents([]); })
      .finally(() => setLoading(false));
  }, [base, classId, date]);

  useEffect(() => { fetchRecords(); }, [fetchRecords]);

  // ── Stats ─────────────────────────────────────────────────────────────────
  const present = records.filter((r) => r.status === "present");
  const uniqueStudents = new Set(records.map((r) => r.student_id)).size;
  const avgConfidence =
    present.length > 0
      ? present.reduce((a, r) => a + (r.confidence ?? 0), 0) / present.length
      : 0;
  const selectedClass = classes.find((c) => String(c.id) === classId);

  // ── Export CSV (client-side) ──────────────────────────────────────────────
  const exportCSV = () => {
    const rows = [
      ["Timestamp", "Student ID", "Student Name", "Status", "Confidence", "Method"],
      ...records.map((r) => [
        new Date(r.timestamp).toLocaleString("vi-VN"),
        r.student_id,
        r.student_name || "",
        r.status,
        r.confidence != null ? (r.confidence * 100).toFixed(2) + "%" : "",
        r.method || "",
      ]),
    ];
    const csv = "\uFEFF" + rows.map((row) => row.map((v) => `"${v}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `attendance_${selectedClass?.class_name ?? "class" + classId}_${date}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Export Excel (server-side) ────────────────────────────────────────────
  const exportExcel = async () => {
    if (!classId) return;
    setExportingXlsx(true);
    try {
      const dateParam = date ? `&date=${encodeURIComponent(date + "T00:00:00")}` : "";
      const res = await fetch(
        `${base}/api/attendance/export?class_id=${classId}${dateParam}`,
        { headers: { Authorization: `Bearer ${getToken()}` } }
      );
      if (!res.ok) throw new Error("Export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const name = selectedClass?.class_name ?? `class${classId}`;
      a.download = `attendance_${name.replace(/\s+/g, "_")}_${date}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (_e) {
      alert("Excel export failed. Please try again.");
    } finally {
      setExportingXlsx(false);
    }
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Attendance Reports</h1>
          <p className="text-gray-400 text-sm mt-0.5">View and export attendance records by class and date</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCSV}
            disabled={records.length === 0}
            className="flex items-center gap-2 bg-white border border-gray-200 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Download className="w-4 h-4" /> CSV
          </button>
          <button
            onClick={exportExcel}
            disabled={!classId || exportingXlsx}
            className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <FileSpreadsheet className="w-4 h-4" />
            {exportingXlsx ? "Exporting…" : "Export Excel"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        <div className="flex items-center gap-2">
          <label className="text-sm text-gray-500 whitespace-nowrap">Class</label>
          <select
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
            disabled={classesLoading}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white min-w-[160px]"
          >
            {classesLoading && <option>Loading classes…</option>}
            {classes.map((c) => (
              <option key={c.id} value={c.id}>{c.class_name}</option>
            ))}
            {!classesLoading && classes.length === 0 && <option value="">No classes found</option>}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <CalendarDays className="w-4 h-4 text-gray-400" />
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white"
          />
        </div>

        <button
          onClick={() => setDate(new Date().toISOString().slice(0, 10))}
          className="text-xs text-blue-600 hover:underline px-2"
        >
          Today
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-1">
            <FileText className="w-4 h-4 text-gray-400" />
            <p className="text-xs text-gray-400 uppercase tracking-wide">Total Records</p>
          </div>
          <p className="text-3xl font-bold text-gray-800">{records.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircle2 className="w-4 h-4 text-green-400" />
            <p className="text-xs text-gray-400 uppercase tracking-wide">Present</p>
          </div>
          <p className="text-3xl font-bold text-green-600">{present.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-1">
            <UserX className="w-4 h-4 text-red-400" />
            <p className="text-xs text-gray-400 uppercase tracking-wide">Absent</p>
          </div>
          <p className="text-3xl font-bold text-red-500">{absentStudents.length}</p>
        </div>
        <div className="bg-white rounded-xl p-5 shadow-sm border border-gray-100">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs text-gray-400">🎯</span>
            <p className="text-xs text-gray-400 uppercase tracking-wide">Avg Confidence</p>
          </div>
          <p className="text-3xl font-bold text-purple-600">
            {present.length > 0 ? `${(avgConfidence * 100).toFixed(1)}%` : "—"}
          </p>
        </div>
      </div>

      {/* Absent students panel */}
      {absentStudents.length > 0 && (
        <div className="mb-6">
          <button
            onClick={() => setShowAbsent((v) => !v)}
            className="flex items-center gap-2 text-sm font-medium text-red-600 hover:text-red-700 mb-2"
          >
            <UserX className="w-4 h-4" />
            {absentStudents.length} student{absentStudents.length !== 1 ? "s" : ""} absent
            <span className="text-gray-400 text-xs">{showAbsent ? "▲ hide" : "▼ show"}</span>
          </button>
          {showAbsent && (
            <div className="bg-red-50 border border-red-100 rounded-xl p-4 flex flex-wrap gap-2">
              {absentStudents.map((s) => (
                <span
                  key={s.student_id}
                  className="inline-flex items-center gap-1 bg-white border border-red-200 text-red-700 text-xs px-3 py-1.5 rounded-full"
                >
                  <UserX className="w-3 h-3" />
                  {s.student_name} <span className="text-red-400">({s.student_code})</span>
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Attendance Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-16">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          </div>
        ) : records.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <FileText className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p className="font-medium">No records found</p>
            <p className="text-sm mt-1">
              {classId ? `No attendance for ${selectedClass?.class_name ?? "this class"} on ${date}` : "Select a class above"}
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Timestamp</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Student</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Status</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Confidence</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Method</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {records
                .slice()
                .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
                .map((r, i) => (
                  <tr key={i} className="hover:bg-gray-50/60 transition-colors">
                    <td className="px-6 py-3 text-gray-500 whitespace-nowrap">
                      {new Date(r.timestamp).toLocaleString("vi-VN")}
                    </td>
                    <td className="px-6 py-3 font-medium text-gray-800">
                      {r.student_name || <span className="text-gray-400">#{r.student_id}</span>}
                    </td>
                    <td className="px-6 py-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          r.status === "present"
                            ? "bg-green-100 text-green-700"
                            : "bg-red-100 text-red-700"
                        }`}
                      >
                        {r.status === "present" ? "✓ Present" : "✗ Absent"}
                      </span>
                    </td>
                    <td className="px-6 py-3 font-mono text-gray-600">
                      {r.confidence != null ? (
                        <span className={r.confidence >= 0.7 ? "text-green-600" : "text-yellow-600"}>
                          {(r.confidence * 100).toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-gray-400 text-xs">
                      {r.method ?? "—"}
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
