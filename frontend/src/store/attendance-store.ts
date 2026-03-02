import { create } from "zustand";
import { AttendanceRecord } from "@/types/attendance";

interface AttendanceState {
  records: AttendanceRecord[];
  realtimeRecords: AttendanceRecord[];
  addRealtimeRecord: (record: AttendanceRecord) => void;
  setRecords: (records: AttendanceRecord[]) => void;
}

export const useAttendanceStore = create<AttendanceState>((set) => ({
  records: [],
  realtimeRecords: [],
  addRealtimeRecord: (record) =>
    set((state) => ({
      realtimeRecords: [record, ...state.realtimeRecords].slice(0, 50),
    })),
  setRecords: (records) => set({ records }),
}));
