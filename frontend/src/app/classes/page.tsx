"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";
import { BookOpen, Plus } from "lucide-react";

interface Class {
  id: number;
  class_code: string;
  class_name: string;
  subject: string | null;
  room: string | null;
  semester: string | null;
  status: string;
}

export default function ClassesPage() {
  const [classes, setClasses] = useState<Class[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ class_code: "", class_name: "", subject: "", room: "", semester: "" });
  const [saving, setSaving] = useState(false);

  const base = getApiBase();
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  const fetchClasses = () => {
    fetch(`${base}/api/classes/`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json()).then(setClasses).catch(() => setClasses([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchClasses(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    await fetch(`${base}/api/classes/`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setSaving(false);
    setShowForm(false);
    setForm({ class_code: "", class_name: "", subject: "", room: "", semester: "" });
    fetchClasses();
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Class Management</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" /> New Class
        </button>
      </div>

      {/* Create Form */}
      {showForm && (
        <form onSubmit={handleCreate} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6 grid grid-cols-2 gap-4">
          {[
            { name: "class_code", label: "Class Code", required: true },
            { name: "class_name", label: "Class Name", required: true },
            { name: "subject", label: "Subject" },
            { name: "room", label: "Room" },
            { name: "semester", label: "Semester" },
          ].map(({ name, label, required }) => (
            <div key={name}>
              <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
              <input
                required={required}
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={(form as Record<string, string>)[name]}
                onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
              />
            </div>
          ))}
          <div className="col-span-2 flex gap-3">
            <button type="submit" disabled={saving} className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-60">
              {saving ? "Saving..." : "Create Class"}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="border border-gray-200 px-4 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
          </div>
        </form>
      )}

      {/* Classes grid */}
      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {classes.map((c) => (
            <div key={c.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-blue-50 rounded-lg">
                  <BookOpen className="w-5 h-5 text-blue-600" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-gray-800 truncate">{c.class_name}</p>
                  <p className="text-xs font-mono text-gray-400">{c.class_code}</p>
                </div>
              </div>
              <div className="mt-3 text-sm text-gray-500 space-y-1">
                {c.subject && <p>📚 {c.subject}</p>}
                {c.room && <p>🚪 {c.room}</p>}
                {c.semester && <p>📅 {c.semester}</p>}
              </div>
              <div className="mt-3">
                <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                  c.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
                }`}>
                  {c.status === "active" ? "Active" : "Inactive"}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
