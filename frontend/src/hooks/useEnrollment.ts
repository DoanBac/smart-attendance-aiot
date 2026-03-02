import { useState } from "react";

export function useEnrollment() {
  const [progress, setProgress] = useState(0);
  const [isScanning, setIsScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEnrollment = async (studentId: string) => {
    setIsScanning(true);
    setProgress(0);
    setError(null);
    try {
      const res = await fetch(`/api/students/${studentId}/enroll`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Đăng ký thất bại");
      setProgress(100);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsScanning(false);
    }
  };

  return { progress, isScanning, error, startEnrollment };
}
