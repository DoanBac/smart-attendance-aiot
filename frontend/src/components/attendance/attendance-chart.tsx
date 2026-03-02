"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

interface AttendanceData {
  date: string;
  present: number;
  absent: number;
  late: number;
}

interface AttendanceChartProps {
  data: AttendanceData[];
}

export default function AttendanceChart({ data }: AttendanceChartProps) {
  return (
    <ResponsiveContainer width="100%" height={350}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis />
        <Tooltip />
        <Legend />
        <Bar dataKey="present" name="Có mặt" fill="#22c55e" />
        <Bar dataKey="absent" name="Vắng mặt" fill="#ef4444" />
        <Bar dataKey="late" name="Đi muộn" fill="#f59e0b" />
      </BarChart>
    </ResponsiveContainer>
  );
}
