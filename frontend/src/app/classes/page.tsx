"use client";
import { useEffect, useState, useCallback } from "react";
import { apiFetch } from "@/lib/api";
import { BookOpen, Plus, X, Pencil } from "lucide-react";

interface Schedule {
  days: string[];
  start_time: string;
  end_time: string;
}

interface ClassItem {
  id: number;
  class_code: string;
  class_name: string;
  subject: string | null;
  room: string | null;
  semester: string | null;
  academic_year: string | null;
  capacity: number | null;
  schedule: Schedule | null;
  status: string;
  student_count: number;
}

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const EMPTY_FORM = {
  class_code: "",
  class_name: "",
  subject: "",
  room: "",
  semester: "",
  academic_year: "",
  capacity: "",
  days: [] as string[],
  start_time: "",
  end_time: "",
};

type FormState = typeof EMPTY_FORM;

function classToForm(c: ClassItem): FormState {
  return {
    class_code: c.class_code,
    class_name: c.class_name,
    subject: c.subject ?? "",
    room: c.room ?? "",
    semester: c.semester ?? "",
    academic_year: c.academic_year ?? "",
    capacity: c.capacity != null ? String(c.capacity) : "",
    days: c.schedule?.days ?? [],
    start_time: c.schedule?.start_time ?? "",
    end_time: c.schedule?.end_time ?? "",
  };
}

function formToBody(f: FormState) {
  const body: Record<string, unknown> = {
    class_name: f.class_name.trim(),
    subject: f.subject.trim() || null,
    room: f.room.trim() || null,
    semester: f.semester.trim() || null,
    academic_year: f.academic_year.trim() || null,
    capacity: f.capacity ? Number(f.capacity) : null,
  };
  // Only send class_code if admin typed one; otherwise let backend auto-gen UUID
  if (f.class_code.trim()) body.class_code = f.class_code.trim().toUpperCase();
  if (f.days.length > 0 || f.start_time || f.end_time) {
    body.schedule = { days: f.days, start_time: f.start_time, end_time: f.end_time };
  }
  return body;
}

export default function ClassesPage() {
  const [classes, setClasses] = useState<ClassItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [semesterFilter, setSemesterFilter] = useState("");

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formErr, setFormErr] = useState("");

  const [editTarget, setEditTarget] = useState<ClassItem | null>(null);
  const [editForm, setEditForm] = useState<FormState>(EMPTY_FORM);
  const [editSaving, setEditSaving] = useState(false);
  const [editErr, setEditErr] = useState("");

  const fetchClasses = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (semesterFilter) params.set("semester", semesterFilter);
      const r = await apiFetch(`/api/classes/?${params}`);
      const d = await r.json();
      setClasses(Array.isArray(d) ? d : d.items ?? []);
    } catch {
      setClasses([]);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, semesterFilter]);

  useEffect(() => { fetchClasses(); }, [fetchClasses]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.class_name.trim()) { setFormErr("Class name is required."); return; }
    setSaving(true); setFormErr("");
    try {
      const r = await apiFetch("/api/classes/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formToBody(form)),
      });
      if (!r.ok) { const err = await r.json(); setFormErr(err.detail ?? "Failed."); return; }
      setShowCreate(false); setForm(EMPTY_FORM);
      await fetchClasses();
    } catch { setFormErr("Network error."); }
    finally { setSaving(false); }
  };

  const handleEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editTarget) return;
    setEditSaving(true); setEditErr("");
    try {
      const r = await apiFetch(`/api/classes/${editTarget.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formToBody(editForm)),
      });
      if (!r.ok) { const err = await r.json(); setEditErr(err.detail ?? "Failed."); return; }
      setEditTarget(null);
      await fetchClasses();
    } catch { setEditErr("Network error."); }
    finally { setEditSaving(false); }
  };

  const handleDeactivate = async (id: number) => {
    await apiFetch(`/api/classes/${id}`, { method: "DELETE" });
    await fetchClasses();
  };

  const semesters = Array.from(new Set(classes.map((c) => c.semester).filter(Boolean))) as string[];

  const ClassForm = ({
    f, setF, err, onSubmit, saving: isSaving, onCancel, title,
  }: {
    f: FormState;
    setF: React.Dispatch<React.SetStateAction<FormState>>;
    err: string;
    onSubmit: (e: React.FormEvent) => void;
    saving: boolean;
    onCancel: () => void;
    title: string;
  }) => (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg p-6 my-4">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-gray-800">{title}</h2>
          <button onClick={onCancel} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {[
              { key: "class_code", label: "Mã lớp (tự động nếu để trống)", ph: "CS101-01" },
              { key: "class_name", label: "Tên lớp *" },
              { key: "subject", label: "Subject" },
              { key: "room", label: "Room" },
              { key: "semester", label: "Semester", ph: "2024-1" },
              { key: "academic_year", label: "Academic Year", ph: "2024-2025" },
              { key: "capacity", label: "Capacity", type: "number" },
            ].map(({ key, label, ph, type }) => (
              <div key={key} className={key === "class_name" ? "col-span-2" : ""}>
                <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                <input
                  type={type ?? "text"}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder={ph ?? ""}
                  value={(f as Record<string, string>)[key] ?? ""}
                  onChange={(e) => setF((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>

          {/* Schedule */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">Schedule Days</label>
            <div className="flex flex-wrap gap-2">
              {DAYS.map((d) => (
                <button
                  key={d} type="button"
                  onClick={() => setF((p) => ({
                    ...p,
                    days: p.days.includes(d) ? p.days.filter((x) => x !== d) : [...p.days, d],
                  }))}
                  className={`text-xs px-3 py-1.5 rounded-md font-medium border transition-colors ${f.days.includes(d) ? "bg-blue-600 text-white border-blue-600" : "text-gray-600 border-gray-200 hover:border-blue-400"}`}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {[
              { key: "start_time", label: "Start Time", type: "time" },
              { key: "end_time", label: "End Time", type: "time" },
            ].map(({ key, label, type }) => (
              <div key={key}>
                <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                <input
                  type={type}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={(f as Record<string, string>)[key]}
                  onChange={(e) => setF((p) => ({ ...p, [key]: e.target.value }))}
                />
              </div>
            ))}
          </div>

          {err && <p className="text-sm text-red-500">{err}</p>}
          <div className="flex gap-3 pt-1">
            <button type="submit" disabled={isSaving} className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
              {isSaving ? "Saving..." : "Save"}
            </button>
            <button type="button" onClick={onCancel} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Class Management</h1>
          <p className="text-gray-500 mt-1">{classes.length} class{classes.length !== 1 ? "es" : ""}</p>
        </div>
        <button onClick={() => { setShowCreate(true); setForm(EMPTY_FORM); setFormErr(""); }}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium">
          <Plus className="w-4 h-4" /> New Class
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-6">
        <input
          className="flex-1 min-w-[200px] px-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Search code, name, or subject..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-700"
          value={semesterFilter}
          onChange={(e) => setSemesterFilter(e.target.value)}
        >
          <option value="">All Semesters</option>
          {semesters.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : classes.length === 0 ? (
        <div className="text-center py-16 text-gray-400">No classes found.</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {classes.map((c) => (
            <div key={c.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-blue-50 rounded-lg shrink-0">
                  <BookOpen className="w-5 h-5 text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-800 truncate">{c.class_name}</p>
                  <p className="text-xs font-mono text-gray-400">{c.class_code}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={() => { setEditTarget(c); setEditForm(classToForm(c)); setEditErr(""); }}
                    className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors" title="Edit">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>

              <div className="mt-3 space-y-1 text-sm text-gray-500">
                {c.subject && <p>Subject: <span className="text-gray-700">{c.subject}</span></p>}
                {c.room && <p>Room: <span className="text-gray-700">{c.room}</span></p>}
                {c.semester && <p>Semester: <span className="text-gray-700">{c.semester}{c.academic_year ? ` / ${c.academic_year}` : ""}</span></p>}
                {c.schedule && (
                  <p>
                    Schedule: <span className="text-gray-700">
                      {c.schedule.days.join(", ")}
                      {c.schedule.start_time ? ` ${c.schedule.start_time}` : ""}
                      {c.schedule.end_time ? ` - ${c.schedule.end_time}` : ""}
                    </span>
                  </p>
                )}
              </div>

              <div className="mt-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {c.status}
                  </span>
                  {c.capacity != null ? (
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${c.student_count >= c.capacity ? "bg-red-100 text-red-600" : "bg-blue-50 text-blue-700"}`}>
                      {c.student_count}/{c.capacity} students
                    </span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-50 text-gray-500">
                      {c.student_count} students
                    </span>
                  )}
                </div>
                {c.status === "active" && (
                  <button onClick={() => handleDeactivate(c.id)}
                    className="text-xs text-gray-400 hover:text-red-500 transition-colors">
                    Deactivate
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <ClassForm
          f={form} setF={setForm} err={formErr}
          onSubmit={handleCreate} saving={saving}
          onCancel={() => setShowCreate(false)}
          title="Create New Class"
        />
      )}

      {editTarget && (
        <ClassForm
          f={editForm} setF={setEditForm} err={editErr}
          onSubmit={handleEdit} saving={editSaving}
          onCancel={() => setEditTarget(null)}
          title={`Edit: ${editTarget.class_name}`}
        />
      )}
    </div>
  );
}
