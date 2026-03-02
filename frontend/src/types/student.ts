export interface Student {
  id: string;
  student_id: string;
  full_name: string;
  email: string;
  class_name: string;
  face_enrolled: boolean;
  created_at: string;
}

export interface StudentCreate {
  student_id: string;
  full_name: string;
  email: string;
  class_name: string;
}
