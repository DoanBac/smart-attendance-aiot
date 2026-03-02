export interface AttendanceRecord {
  id: string;
  student_id: string;
  student_name: string;
  class_name: string;
  check_in_time: string;
  status: "present" | "late" | "absent";
  device_id: string;
  confidence: number;
}

export interface AttendanceStats {
  date: string;
  present: number;
  absent: number;
  late: number;
}
