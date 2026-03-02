import { useState, useEffect } from "react";
import { AttendanceRecord } from "@/types/attendance";

export function useAttendance(date?: string) {
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchAttendance = async () => {
      setLoading(true);
      try {
        const params = date ? `?date=${date}` : "";
        const res = await fetch(`/api/attendance${params}`);
        const data = await res.json();
        setRecords(data);
      } catch (e) {
        setError("Không thể tải dữ liệu điểm danh");
      } finally {
        setLoading(false);
      }
    };
    fetchAttendance();
  }, [date]);

  return { records, loading, error };
}
