"use client";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import Link from "next/link";
import { UserPlus, Search, Plus, X, UserX, UserCheck, BookOpen, Pencil } from "lucide-react";

interface ClassBrief {
  id: string;
  class_code: string;
  class_name: string;
  subject: string | null;
  schedule: { days: string[]; start_time: string; end_time: string } | null;
}

interface Student {
  id: string;
  student_code: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  has_face: boolean;
  enrolled_classes: ClassBrief[];
}

interface ClassOption {
  id: string;
  class_code: string;
  class_name: string;
  subject: string | null;
}

const EMPTY_FORM = {
  full_name: "",
  email: "",
  phone: "",
  class_ids: [] as string[],
};

export default function StudentsPage() {
  const [students, setStudents] = useState<Student[]>([]);
  const [classes, setClasses] = useState<ClassOption[]>([]);
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [showInactive, setShowInactive] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formErr, setFormErr] = useState("");
  const [classSearch, setClassSearch] = useState("");

  const [enrollTarget, setEnrollTarget] = useState<Student | null>(null);
  const [enrollClassId, setEnrollClassId] = useState("");
  const [enrolling, setEnrolling] = useState(false);
  const [enrollErr, setEnrollErr] = useState("");

  const [confirmDeactivate, setConfirmDeactivate] = useState<Student | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  const [editTarget, setEditTarget] = useState<Student | null>(null);
  const [editForm, setEditForm] = useState({ full_name: "", email: "", phone: "" });
  const [editSaving, setEditSaving] = useState(false);
  const [editErr, setEditErr] = useState("");

  const fetchStudents = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ include_inactive: String(showInactive) });
      if (search) params.set("search", search);
      if (classFilter) params.set("class_id", classFilter);
      const r = await apiFetch(`/api/students/?${params}`);
      const data = await r.json();
      setStudents(Array.isArray(data) ? data : data.items ?? []);
    } catch {
      setStudents([]);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showInactive, search, classFilter]);

  useEffect(() => {
    apiFetch("/api/classes/")
      .then((r) => r.json())
      .then((d) => setClasses(Array.isArray(d) ? d : d.items ?? []))
      .catch(() => setClasses([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { fetchStudents(); }, [fetchStudents]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.full_name.trim()) { setFormErr("Full name is required."); return; }
    setSaving(true); setFormErr("");
    try {
      const body: Record<string, unknown> = {
        full_name: form.full_name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        class_ids: form.class_ids,
      };
      const r = await apiFetch("/api/students/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) { const err = await r.json(); setFormErr(err.detail ?? "Failed."); return; }
      setShowAdd(false); setForm(EMPTY_FORM); setClassSearch("");
      await fetchStudents();
    } catch { setFormErr("Network error."); }
    finally { setSaving(false); }
  };

  const handleEnroll = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!enrollTarget || !enrollClassId) return;
    setEnrolling(true); setEnrollErr("");
    try {
      const r = await apiFetch(`/api/students/${enrollTarget.id}/enroll`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ class_id: enrollClassId }),
      });
      if (!r.ok) { const err = await r.json(); setEnrollErr(err.detail ?? "Failed."); return; }
      setEnrollTarget(null); setEnrollClassId("");
      await fetchStudents();
    } catch { setEnrollErr("Network error."); }
    finally { setEnrolling(false); }
  };

  const handleUnenroll = async (studentId: string, classId: string) => {
    await apiFetch(`/api/students/${studentId}/classes/${classId}`, { method: "DELETE" });
    await fetchStudents();
  };

  const handleDeactivate = async () => {
    if (!confirmDeactivate) return;
    setDeactivating(true);
    try {
      await apiFetch(`/api/students/${confirmDeactivate.id}/deactivate`, { method: "PATCH" });
      setConfirmDeactivate(null);
      await fetchStudents();
    } finally { setDeactivating(false); }
  };

  const handleActivate = async (s: Student) => {
    await apiFetch(`/api/students/${s.id}/activate`, { method: "PATCH" });
    await fetchStudents();
  };

  const openEdit = (s: Student) => {
    setEditTarget(s);
    setEditForm({ full_name: s.full_name, email: s.email ?? "", phone: s.phone ?? "" });
    setEditErr("");
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editTarget || !editForm.full_name.trim()) { setEditErr("Full name is required."); return; }
    setEditSaving(true); setEditErr("");
    try {
      const r = await apiFetch(`/api/students/${editTarget.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: editForm.full_name.trim(),
          email: editForm.email.trim() || null,
          phone: editForm.phone.trim() || null,
        }),
      });
      if (!r.ok) { const err = await r.json(); setEditErr(err.detail ?? "Failed."); return; }
      setEditTarget(null);
      await fetchStudents();
    } catch { setEditErr("Network error."); }
    finally { setEditSaving(false); }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Student Management</h1>
          <p className="text-gray-500 mt-1">
            {students.length} student{students.length !== 1 ? "s" : ""}
            {showInactive ? " (including inactive)" : ""}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/students/enroll"
            className="flex items-center gap-2 border border-blue-600 text-blue-600 px-4 py-2.5 rounded-lg hover:bg-blue-50 transition-colors text-sm font-medium">
            <UserPlus className="w-4 h-4" /> Face Enroll
          </Link>
          <button onClick={() => { setShowAdd(true); setForm(EMPTY_FORM); setFormErr(""); setClassSearch(""); }}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
            <Plus className="w-4 h-4" /> Add Student
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 mb-6">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Search by name, code, or email..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-700"
          value={classFilter}
          onChange={(e) => setClassFilter(e.target.value)}
        >
          <option value="">All Classes</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>{c.class_name} ({c.class_code})</option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm text-gray-600 select-none cursor-pointer">
          <input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} className="rounded" />
          Show inactive
        </label>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : students.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No students found.</div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {students.map((s) => (
            <div key={s.id} className={`bg-white rounded-xl border shadow-sm p-5 hover:shadow-md transition-shadow ${s.status !== "active" ? "opacity-60" : ""}`}>
              <div className="flex items-start justify-between gap-2 mb-3">
                <div className="min-w-0">
                  <p className="font-semibold text-gray-900 truncate">{s.full_name}</p>
                  <p className="text-xs font-mono text-gray-400 mt-0.5">{s.student_code}</p>
                  {s.email && <p className="text-xs text-gray-500 truncate mt-0.5">{s.email}</p>}
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  {s.has_face && <span className="text-xs bg-purple-100 text-purple-700 px-2 py-0.5 rounded-full font-medium">Face OK</span>}
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>{s.status}</span>
                </div>
              </div>

              <div className="mb-3">
                <p className="text-xs font-medium text-gray-500 mb-1.5">Enrolled Classes</p>
                <div className="flex flex-wrap gap-1">
                  {s.enrolled_classes.length === 0 ? (
                    <span className="text-xs text-gray-300 italic">None</span>
                  ) : s.enrolled_classes.map((c) => (
                    <span key={c.id} className="inline-flex items-center gap-1 text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded-md font-medium">
                      <BookOpen className="w-3 h-3" />
                      {c.class_name}
                      <button onClick={() => handleUnenroll(s.id, c.id)} className="ml-0.5 text-blue-400 hover:text-red-500 transition-colors" title="Remove">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-3 border-t border-gray-100">
                <button onClick={() => openEdit(s)}
                  className="flex items-center gap-1.5 text-xs bg-gray-50 text-gray-700 hover:bg-gray-100 px-3 py-1.5 rounded-md font-medium transition-colors border border-gray-200">
                  <Pencil className="w-3.5 h-3.5" /> Edit
                </button>
                <button onClick={() => { setEnrollTarget(s); setEnrollClassId(""); setEnrollErr(""); }}
                  className="flex items-center gap-1.5 text-xs bg-blue-50 text-blue-700 hover:bg-blue-100 px-3 py-1.5 rounded-md font-medium transition-colors">
                  <Plus className="w-3.5 h-3.5" /> Enroll
                </button>
                {s.status === "active" ? (
                  <button onClick={() => setConfirmDeactivate(s)}
                    className="flex items-center gap-1.5 text-xs text-red-500 hover:bg-red-50 px-3 py-1.5 rounded-md font-medium transition-colors">
                    <UserX className="w-3.5 h-3.5" /> Deactivate
                  </button>
                ) : (
                  <button onClick={() => handleActivate(s)}
                    className="flex items-center gap-1.5 text-xs text-green-600 hover:bg-green-50 px-3 py-1.5 rounded-md font-medium transition-colors">
                    <UserCheck className="w-3.5 h-3.5" /> Activate
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showAdd && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-gray-800">Add New Student</h2>
              <button onClick={() => { setShowAdd(false); setClassSearch(""); }} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <form onSubmit={handleAdd} className="space-y-4">
              {[
                { key: "full_name", label: "Full Name *", ph: "David Do" },
                { key: "email", label: "Email", ph: "student@example.com" },
                { key: "phone", label: "Phone Number", ph: "0987654321" },
              ].map(({ key, label, ph }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                  <input
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder={ph}
                    value={(form as Record<string, string>)[key] ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </div>
              ))}
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Enroll in Classes</label>
                <div className="relative mb-1">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400 pointer-events-none" />
                  <input
                    type="text"
                    placeholder="Search classes..."
                    value={classSearch}
                    onChange={(e) => setClassSearch(e.target.value)}
                    className="w-full pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  {classSearch && (
                    <button type="button" onClick={() => setClassSearch("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </div>
                <div className="border border-gray-200 rounded-lg p-2 max-h-44 overflow-y-auto space-y-0.5">
                  {(() => {
                    const q = classSearch.toLowerCase();
                    const filtered = classes.filter(
                      (c) =>
                        c.class_name.toLowerCase().includes(q) ||
                        c.class_code.toLowerCase().includes(q) ||
                        (c.subject ?? "").toLowerCase().includes(q)
                    );
                    if (classes.length === 0) return <p className="text-sm text-gray-400 italic py-2 text-center">No classes available</p>;
                    if (filtered.length === 0) return <p className="text-sm text-gray-400 italic py-2 text-center">No matching classes</p>;
                    return filtered.map((c) => (
                      <label key={c.id} className="flex items-center gap-2 text-sm cursor-pointer hover:bg-gray-50 px-2 py-1 rounded">
                        <input
                          type="checkbox"
                          checked={form.class_ids.includes(c.id)}
                          onChange={(e) => setForm((f) => ({
                            ...f,
                            class_ids: e.target.checked ? [...f.class_ids, c.id] : f.class_ids.filter((i) => i !== c.id),
                          }))}
                          className="rounded accent-blue-600"
                        />
                        <span className="flex-1 text-gray-700">{c.class_name}</span>
                        <span className="text-gray-400 text-xs font-mono shrink-0">({c.class_code})</span>
                      </label>
                    ));
                  })()}
                </div>
                {form.class_ids.length > 0 && (
                  <p className="text-xs text-blue-600 mt-1">{form.class_ids.length} class{form.class_ids.length > 1 ? "es" : ""} selected</p>
                )}
              </div>
              {formErr && <p className="text-sm text-red-500">{formErr}</p>}
              <div className="flex gap-3 pt-1">
                <button type="submit" disabled={saving} className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
                  {saving ? "Saving..." : "Create Student"}
                </button>
                <button type="button" onClick={() => { setShowAdd(false); setClassSearch(""); }} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {enrollTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-800">Enroll in Class</h2>
              <button onClick={() => setEnrollTarget(null)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-sm text-gray-600 mb-4">Student: <strong>{enrollTarget.full_name}</strong></p>
            <form onSubmit={handleEnroll} className="space-y-4">
              <select required value={enrollClassId} onChange={(e) => setEnrollClassId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                <option value="">Select a class</option>
                {classes.filter((c) => !enrollTarget.enrolled_classes.some((ec) => ec.id === c.id)).map((c) => (
                  <option key={c.id} value={c.id}>{c.class_name} ({c.class_code})</option>
                ))}
              </select>
              {enrollErr && <p className="text-sm text-red-500">{enrollErr}</p>}
              <div className="flex gap-3">
                <button type="submit" disabled={enrolling || !enrollClassId}
                  className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
                  {enrolling ? "Enrolling..." : "Enroll"}
                </button>
                <button type="button" onClick={() => setEnrollTarget(null)} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {editTarget && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-gray-800">Edit Student</h2>
              <button onClick={() => setEditTarget(null)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <form onSubmit={handleEdit} className="space-y-4">
              {[
                { key: "full_name", label: "Full Name *", ph: "Nguyen Van A" },
                { key: "email", label: "Email", ph: "student@example.com" },
                { key: "phone", label: "Phone", ph: "0987654321" },
              ].map(({ key, label, ph }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                  <input
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder={ph}
                    value={(editForm as Record<string, string>)[key] ?? ""}
                    onChange={(e) => setEditForm((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </div>
              ))}
              {editErr && <p className="text-sm text-red-500">{editErr}</p>}
              <div className="flex gap-3 pt-1">
                <button type="submit" disabled={editSaving} className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
                  {editSaving ? "Saving..." : "Save Changes"}
                </button>
                <button type="button" onClick={() => setEditTarget(null)} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {confirmDeactivate && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6 text-center">
            <UserX className="w-10 h-10 text-red-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-800 mb-2">Deactivate Student?</h2>
            <p className="text-sm text-gray-500 mb-5">This will mark <strong>{confirmDeactivate.full_name}</strong> as inactive.</p>
            <div className="flex gap-3">
              <button onClick={handleDeactivate} disabled={deactivating}
                className="flex-1 bg-red-500 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-600 disabled:opacity-60">
                {deactivating ? "Deactivating..." : "Deactivate"}
              </button>
              <button onClick={() => setConfirmDeactivate(null)} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
