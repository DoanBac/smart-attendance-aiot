"use client";
import { useEffect, useState, useCallback } from "react";
import { getApiBase } from "@/lib/api";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft, User, Camera, Pencil, X, Save,
  UserX, UserCheck, AlertTriangle, CheckCircle, XCircle,
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
  enrollment_date: string;
}

interface ClassOption {
  id: number;
  class_name: string;
}

export default function StudentDetailPage() {
  const { id } = useParams();
  const router = useRouter();

  const [student, setStudent] = useState<Student | null>(null);
  const [classes, setClasses] = useState<ClassOption[]>([]);
  const [loading, setLoading] = useState(true);

  // Edit mode
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ full_name: "", email: "", phone: "", class_id: "" });
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState("");
  const [saveOk, setSaveOk] = useState(false);

  // Deactivate confirm
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [deactivating, setDeactivating] = useState(false);

  const base = getApiBase();
  const getToken = () =>
    typeof window !== "undefined" ? localStorage.getItem("access_token") ?? "" : "";

  const fetchStudent = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${base}/api/students/${id}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (r.status === 404) { setStudent(null); return; }
      const data: Student = await r.json();
      setStudent(data);
      setEditForm({
        full_name: data.full_name,
        email: data.email ?? "",
        phone: data.phone ?? "",
        class_id: data.class_id?.toString() ?? "",
      });
    } finally {
      setLoading(false);
    }
  }, [base, id]);

  useEffect(() => {
    fetch(`${base}/api/classes/`, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.json())
      .then((d) => setClasses(Array.isArray(d) ? d : d.items ?? []))
      .catch(() => {});
  }, [base]);

  useEffect(() => { fetchStudent(); }, [fetchStudent]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editForm.full_name.trim()) { setSaveErr("Full name is required."); return; }
    setSaving(true); setSaveErr(""); setSaveOk(false);
    try {
      const body: Record<string, unknown> = {
        full_name: editForm.full_name.trim(),
        email: editForm.email.trim() || null,
        phone: editForm.phone.trim() || null,
        class_id: editForm.class_id ? Number(editForm.class_id) : null,
      };
      const r = await fetch(`${base}/api/students/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify(body),
      });
      if (!r.ok) { const err = await r.json(); setSaveErr(err.detail ?? "Failed to save."); return; }
      await fetchStudent();
      setEditing(false); setSaveOk(true);
      setTimeout(() => setSaveOk(false), 3000);
    } catch { setSaveErr("Network error."); }
    finally { setSaving(false); }
  };

  const handleDeactivate = async () => {
    setDeactivating(true);
    try {
      await fetch(`${base}/api/students/${id}/deactivate`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      setConfirmDeactivate(false);
      await fetchStudent();
    } finally { setDeactivating(false); }
  };

  const handleActivate = async () => {
    await fetch(`${base}/api/students/${id}/activate`, {
      method: "PATCH",
      headers: { Authorization: `Bearer ${getToken()}` },
    });
    await fetchStudent();
  };

  if (loading) return (
    <div className="flex justify-center py-20">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
    </div>
  );

  if (!student) return (
    <div className="p-8">
      <p className="text-gray-500">Student not found.</p>
      <Link href="/students" className="text-blue-600 hover:underline text-sm mt-2 block">← Back to Students</Link>
    </div>
  );

  const className =
    student.class_id
      ? (classes.find((c) => c.id === student.class_id)?.class_name ?? `Class ${student.class_id}`)
      : "—";

  return (
    <div className="p-8 max-w-2xl">
      <Link href="/students" className="flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 text-sm w-fit">
        <ArrowLeft className="w-4 h-4" /> Back to Students
      </Link>

      {saveOk && (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 text-green-700 rounded-lg px-4 py-3 mb-4 text-sm">
          <CheckCircle className="w-4 h-4" /> Student information updated successfully.
        </div>
      )}

      <div className="bg-white rounded-xl shadow-sm border border-gray-100">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-gray-100">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 bg-blue-100 rounded-full flex items-center justify-center">
              <User className="w-7 h-7 text-blue-600" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-800">{student.full_name}</h1>
              <p className="text-gray-500 font-mono text-sm">{student.student_code}</p>
            </div>
          </div>
          <span className={`px-3 py-1 rounded-full text-xs font-semibold ${
            student.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"
          }`}>
            {student.status === "active" ? "Active" : "Inactive"}
          </span>
        </div>

        <div className="px-6 py-5">
          {!editing ? (
            <>
              <div className="grid grid-cols-2 gap-4 text-sm mb-6">
                {([
                  ["Email", student.email || "—"],
                  ["Phone", student.phone || "—"],
                  ["Class", className],
                  ["Enrolled on", new Date(student.enrollment_date).toLocaleDateString("en-US")],
                ] as [string, string][]).map(([label, value]) => (
                  <div key={label} className="bg-gray-50 rounded-lg p-3">
                    <p className="text-gray-400 text-xs mb-1">{label}</p>
                    <p className="font-medium text-gray-700">{value}</p>
                  </div>
                ))}
                <div className="bg-gray-50 rounded-lg p-3 col-span-2">
                  <p className="text-gray-400 text-xs mb-1">Face</p>
                  {student.has_face ? (
                    <span className="flex items-center gap-1 text-green-600 font-medium text-sm">
                      <CheckCircle className="w-4 h-4" /> Registered
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-orange-500 font-medium text-sm">
                      <XCircle className="w-4 h-4" /> Not registered
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 flex-wrap">
                <button
                  onClick={() => { setEditing(true); setSaveErr(""); }}
                  className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 transition-colors"
                >
                  <Pencil className="w-4 h-4" /> Edit Info
                </button>

                {!student.has_face && student.status === "active" && (
                  <Link
                    href={`/students/enroll?student_id=${student.id}`}
                    className="flex items-center gap-2 bg-orange-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-orange-600 transition-colors"
                  >
                    <Camera className="w-4 h-4" /> Register Face
                  </Link>
                )}

                {student.status === "active" ? (
                  <button
                    onClick={() => setConfirmDeactivate(true)}
                    className="flex items-center gap-2 border border-red-300 text-red-600 px-4 py-2 rounded-lg text-sm hover:bg-red-50 transition-colors"
                  >
                    <UserX className="w-4 h-4" /> Deactivate
                  </button>
                ) : (
                  <button
                    onClick={handleActivate}
                    className="flex items-center gap-2 border border-green-300 text-green-600 px-4 py-2 rounded-lg text-sm hover:bg-green-50 transition-colors"
                  >
                    <UserCheck className="w-4 h-4" /> Activate
                  </button>
                )}
              </div>
            </>
          ) : (
            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Full Name <span className="text-red-500">*</span></label>
                <input type="text" value={editForm.full_name}
                  onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input type="email" value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                <input type="text" value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Class</label>
                <select value={editForm.class_id}
                  onChange={(e) => setEditForm({ ...editForm, class_id: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
                  <option value="">— No class assigned —</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>{c.class_name}</option>
                  ))}
                </select>
              </div>

              {saveErr && (
                <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{saveErr}</p>
              )}

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setEditing(false)}
                  className="flex items-center gap-2 flex-1 justify-center border border-gray-200 text-gray-600 py-2 rounded-lg text-sm hover:bg-gray-50">
                  <X className="w-4 h-4" /> Cancel
                </button>
                <button type="submit" disabled={saving}
                  className="flex items-center gap-2 flex-1 justify-center bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
                  <Save className="w-4 h-4" />
                  {saving ? "Saving…" : "Save Changes"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      {/* Confirm Deactivate Modal */}
      {confirmDeactivate && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <AlertTriangle className="w-6 h-6 text-red-600" />
            </div>
            <h2 className="text-center text-lg font-semibold text-gray-800 mb-2">Deactivate Student?</h2>
            <p className="text-center text-sm text-gray-500 mb-6">
              <span className="font-medium text-gray-700">{student.full_name}</span> will be set to inactive
              and their face biometric data permanently erased.
              <br />
              <span className="text-xs text-gray-400">Attendance history is preserved. You can re-activate later.</span>
            </p>
            <div className="flex gap-3">
              <button onClick={() => setConfirmDeactivate(false)}
                className="flex-1 border border-gray-200 text-gray-600 py-2 rounded-lg text-sm hover:bg-gray-50">
                Cancel
              </button>
              <button onClick={handleDeactivate} disabled={deactivating}
                className="flex-1 bg-red-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-60">
                {deactivating ? "Deactivating…" : "Yes, Deactivate"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}