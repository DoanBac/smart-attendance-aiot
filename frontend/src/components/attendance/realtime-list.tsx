"use client";
import { useAttendanceStore } from "@/store/attendance-store";
import { Badge } from "@/components/ui/badge";

export default function RealtimeList() {
  const records = useAttendanceStore((s) => s.realtimeRecords);

  return (
    <div className="space-y-2">
      {records.length === 0 && (
        <p className="text-sm text-gray-500 text-center py-4">Chưa có dữ liệu realtime</p>
      )}
      {records.map((r) => (
        <div key={r.id} className="flex items-center justify-between p-3 border rounded-lg">
          <div>
            <p className="font-medium text-sm">{r.student_name}</p>
            <p className="text-xs text-gray-500">{r.class_name} · {r.check_in_time}</p>
          </div>
          <Badge variant={r.status === "present" ? "success" : r.status === "late" ? "warning" : "destructive"}>
            {r.status === "present" ? "Có mặt" : r.status === "late" ? "Muộn" : "Vắng"}
          </Badge>
        </div>
      ))}
    </div>
  );
}
