import { Student } from "@/types/student";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";

export default function StudentTable({ students }: { students: Student[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Mã SV</TableHead>
          <TableHead>Họ tên</TableHead>
          <TableHead>Lớp</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Face ID</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {students.map((s) => (
          <TableRow key={s.id}>
            <TableCell>{s.student_id}</TableCell>
            <TableCell>{s.full_name}</TableCell>
            <TableCell>{s.class_name}</TableCell>
            <TableCell>{s.email}</TableCell>
            <TableCell>
              <Badge variant={s.face_enrolled ? "success" : "warning"}>
                {s.face_enrolled ? "Đã đăng ký" : "Chưa đăng ký"}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
