"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, User, Camera } from "lucide-react";

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

export default function StudentDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [student, setStudent] = useState<Student | null>(null);
  const [loading, setLoading] = useState(true);

  const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  useEffect(() => {
    fetch(`${base}/api/students/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => r.json())
      .then(setStudent)
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <div className="flex justify-center py-20"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>;
  if (!student) return <div className="p-8 text-gray-500">Student not found.</div>;

  return (
    <div className="p-8 max-w-2xl">
      <Link href="/students" className="flex items-center gap-2 text-gray-500 hover:text-gray-700 mb-6 text-sm">
        <ArrowLeft className="w-4 h-4" /> Back
      </Link>

      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center">
            <User className="w-8 h-8 text-blue-600" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-800">{student.full_name}</h1>
            <p className="text-gray-500 font-mono text-sm">{student.student_code}</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm">
          {[
            ["Email", student.email || "—"],
            ["Phone", student.phone || "—"],
            ["Class ID", student.class_id?.toString() || "—"],
            ["Status", student.status === "active" ? "Active" : "Inactive"],
            ["Enrolled on", new Date(student.enrollment_date).toLocaleDateString("en-US")],
            ["Face", student.has_face ? "✅ Registered" : "⚠️ Not registered"],
          ].map(([label, value]) => (
            <div key={label} className="bg-gray-50 rounded-lg p-3">
              <p className="text-gray-400 text-xs mb-1">{label}</p>
              <p className="font-medium text-gray-700">{value}</p>
            </div>
          ))}
        </div>

        {!student.has_face && (
          <div className="mt-6 p-4 bg-orange-50 border border-orange-200 rounded-lg">
            <p className="text-orange-700 text-sm font-medium mb-2">⚠️ Face not yet registered</p>
            <Link
              href={`/students/enroll?student_id=${student.id}`}
              className="flex items-center gap-2 bg-orange-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-orange-600 transition-colors w-fit"
            >
              <Camera className="w-4 h-4" /> Register face now
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}