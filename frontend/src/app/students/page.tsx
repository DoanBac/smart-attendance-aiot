"use client";
import { useEffect, useState, useCallback } from "react";
import { getApiBase } from "@/lib/api";
import Link from "next/link";
import {
  UserPlus, Search, CheckCircle, XCircle, Plus, X,
  UserX, UserCheck, Pencil, Eye,
} from "lucide-react";

interface Student {
  id: number;
  student_code: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  class_id: number | null;
  status: string;
  has_face: boolean;
}

interface ClassOption {
  id: number;
  class_name: string;
}

const EMPTY_FORM = {
  full_name: "",
  email: "",
  phone: "",
  class_id: "",
  student_code: "", // leave blank → auto-generated as FSB001, FSB002 …
};

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[]>([]);
  const [classes, setClasses] = useState<ClassOption[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);

  // Add-student modal
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formErr, setFormErr] = useState("");

  // Confirm deactivate
  const [confirmDeactivate, setConfirmDeactivate] = useState<Student | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  const base = getApiBase();
  const getToken = () => (typeof window !== "undefined" ? localStorage.getItem("access_token") ?? "" : "");

  // ── Fetch students ───────────────────────────────────────────────────────
  const fetchStudents = useCallback(async () => {
    setLoading(true);
    try {
      const url = `${base}/api/students/?include_inactive=${showInactive}`;
      const r = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
      const data = await r.json();
      if (Array.isArray(data)) setStudents(data);
      else if (data.items) setStudents(data.items);
      else setStudents([]);
    } catch {
      setStudents([]);
    } finally {
      setLoading(false);
    }
  }, [base, showInactive]);

  // ── Fetch classes for dropdown ───────────────────────────────────────────
  useEffect(() => {
    fetch(`${base}/api/classes/`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((d) => setClasses(Array.isArray(d) ? d : d.items ?? []))
      .catch(() => setClasses([]));
  }, [base]);

  useEffect(() => { fetchStudents(); }, [fetchStudents]);

  // ── Derived list ─────────────────────────────────────────────────────────
  const filtered = students.filter(
    (s) =>
      s.full_name.toLowerCase().includes(search.toLowerCase()) ||
      s.student_code.toLowerCase().includes(search.toLowerCase()) ||
      (s.email ?? "").toLowerCase().includes(search.toLowerCase()),
  );

  // ── Add student ──────────────────────────────────────────────────────────
  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.full_name.trim()) { setFormErr("Full name is required."); return; }
    setSaving(true);
    setFormErr("");
    try {
      const body: Record<string, unknown> = {
        full_name: form.full_name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        class_id: form.class_id ? Number(form.class_id) : null,
      };
      // Only send student_code if admin typed one; otherwise backend auto-generates FSBxxx
      if (form.student_code.trim()) body.student_code = form.student_code.trim().toUpperCase();

      const r = await fetch(`${base}/api/students/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json();
        setFormErr(err.detail ?? "Failed to create student.");
        return;
      }
      setShowAdd(false);
      setForm(EMPTY_FORM);
      await fetchStudents();
    } catch {
      setFormErr("Network error.");
    } finally {
      setSaving(false);
    }
  };

  // ── Soft-delete (deactivate) ─────────────────────────────────────────────
  const handleDeactivate = async () => {
    if (!confirmDeactivate) return;
    setDeactivating(true);
    try {
      await fetch(`${base}/api/students/${confirmDeactivate.id}/deactivate`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      setConfirmDeactivate(null);
      await fetchStudents();
    } finally {
      setDeactivating(false);
    }
  };

  // ── Re-activate ───────────────────────────────────────────────────────────
  const handleActivate = async (s: Student) => {
    await fetch(`${base}/api/students/${s.id}/activate`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    await fetchStudents();
  };

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Student Management</h1>
          <p className="text-gray-500 mt-1">
            {students.length} student{students.length !== 1 ? "s" : ""}
            {showInactive ? " (including inactive)" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Face enrollment link */}
          <Link
            href="/students/enroll"
            className="flex items-center gap-2 border border-blue-600 text-blue-600 px-4 py-2.5 rounded-lg hover:bg-blue-50 transition-colors text-sm font-medium"
          >
            <UserPlus className="w-4 h-4" />
            Face Enroll
          </Link>
          {/* Add new student */}
          <button
            onClick={() => { setShowAdd(true); setForm(EMPTY_FORM); setFormErr(""); }}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            <Plus className="w-4 h-4" />
            Add Student
          </button>
        </div>
      </div>

      {/* Search + filter bar */}
      <div className="flex items-center gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search by name, student code, or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600 select-none cursor-pointer">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="rounded"
          />
          Show inactive
        </label>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {loading ? (
          <div className="flex justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Student ID</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Full Name</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Email</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Class</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Face</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Status</th>
                <th className="text-left px-6 py-3 text-gray-500 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map((s) => (
                <tr
                  key={s.id}
                  className={`hover:bg-gray-50 transition-colors ${s.status !== "active" ? "opacity-50" : ""}`}
                >
                  <td className="px-6 py-4 font-mono text-gray-600 font-semibold">{s.student_code}</td>
                  <td className="px-6 py-4 font-medium text-gray-800">{s.full_name}</td>
                  <td className="px-6 py-4 text-gray-500">{s.email || "—"}</td>
                  <td className="px-6 py-4 text-gray-500">
                    {s.class_id
                      ? (classes.find((c) => c.id === s.class_id)?.class_name ?? `Class ${s.class_id}`)
                      : "—"}
                  </td>
                  <td className="px-6 py-4">
                    {s.has_face ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="w-4 h-4" /> Registered
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-orange-500">
                        <XCircle className="w-4 h-4" /> Not registered
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${
                        s.status === "active"
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {s.status === "active" ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/students/${s.id}`}
                        className="flex items-center gap-1 text-blue-600 hover:text-blue-800 font-medium"
                        title="View / Edit"
                      >
                        <Eye className="w-4 h-4" />
                        View
                      </Link>
                      {s.status === "active" && (
                        <Link
                          href={`/students/enroll?student_id=${s.id}`}
                          className="flex items-center gap-1 text-purple-600 hover:text-purple-800 font-medium"
                          title="Enroll face"
                        >
                          <UserPlus className="w-4 h-4" />
                          Enroll
                        </Link>
                      )}
                      {s.status === "active" ? (
                        <button
                          onClick={() => setConfirmDeactivate(s)}
                          className="flex items-center gap-1 text-red-500 hover:text-red-700 font-medium"
                          title="Deactivate student"
                        >
                          <UserX className="w-4 h-4" />
                          Deactivate
                        </button>
                      ) : (
                        <button
                          onClick={() => handleActivate(s)}
                          className="flex items-center gap-1 text-green-600 hover:text-green-800 font-medium"
                          title="Re-activate student"
                        >
                          <UserCheck className="w-4 h-4" />
                          Activate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-gray-400">
                    No students found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Add Student Modal ──────────────────────────────────────────────── */}
      {showAdd && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h2 className="text-lg font-semibold text-gray-800">Add New Student</h2>
              <button onClick={() => setShowAdd(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleAdd} className="px-6 py-5 space-y-4">
              {/* Full name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Full Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Nguyen Van A"
                />
              </div>

              {/* Student code */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Student ID{" "}
                  <span className="text-gray-400 font-normal text-xs">(leave blank to auto-generate FSB001…)</span>
                </label>
                <input
                  type="text"
                  value={form.student_code}
                  onChange={(e) => setForm({ ...form, student_code: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="FSB042 (optional)"
                />
              </div>

              {/* Email */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="student@school.edu.vn"
                />
              </div>

              {/* Phone */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                <input
                  type="text"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="0901234567"
                />
              </div>

              {/* Class */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Class</label>
                <select
                  value={form.class_id}
                  onChange={(e) => setForm({ ...form, class_id: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">— No class assigned —</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.class_name}
                    </option>
                  ))}
                </select>
              </div>

              {formErr && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {formErr}
                </p>
              )}

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAdd(false)}
                  className="flex-1 border border-gray-200 text-gray-600 py-2 rounded-lg text-sm hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-60"
                >
                  {saving ? "Saving…" : "Add Student"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Confirm Deactivate Modal ───────────────────────────────────────── */}
      {confirmDeactivate && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <UserX className="w-6 h-6 text-red-600" />
            </div>
            <h2 className="text-center text-lg font-semibold text-gray-800 mb-2">Deactivate Student?</h2>
            <p className="text-center text-sm text-gray-500 mb-6">
              <span className="font-medium text-gray-700">{confirmDeactivate.full_name}</span>{" "}
              ({confirmDeactivate.student_code}) will be set to inactive and their face data erased.
              Attendance history is preserved.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmDeactivate(null)}
                className="flex-1 border border-gray-200 text-gray-600 py-2 rounded-lg text-sm hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleDeactivate}
                disabled={deactivating}
                className="flex-1 bg-red-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-60"
              >
                {deactivating ? "Deactivating…" : "Yes, Deactivate"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
