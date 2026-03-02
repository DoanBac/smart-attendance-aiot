"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { StudentCreate } from "@/types/student";

interface StudentFormProps {
  onSubmit: (data: StudentCreate) => void;
  onCancel: () => void;
}

export default function StudentForm({ onSubmit, onCancel }: StudentFormProps) {
  const [form, setForm] = useState<StudentCreate>({
    student_id: "",
    full_name: "",
    email: "",
    class_name: "",
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
      className="space-y-4"
    >
      {(["student_id", "full_name", "email", "class_name"] as const).map(
        (field) => (
          <div key={field}>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              {field}
            </label>
            <input
              name={field}
              value={form[field]}
              onChange={handleChange}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              required
            />
          </div>
        )
      )}
      <div className="flex gap-2 justify-end">
        <Button type="button" variant="outline" onClick={onCancel}>
          Hủy
        </Button>
        <Button type="submit">Lưu</Button>
      </div>
    </form>
  );
}
