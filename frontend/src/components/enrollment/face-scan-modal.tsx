"use client";
import { Dialog, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useEnrollment } from "@/hooks/useEnrollment";

interface FaceScanModalProps {
  open: boolean;
  onClose: () => void;
  studentId: string;
  studentName: string;
}

export default function FaceScanModal({ open, onClose, studentId, studentName }: FaceScanModalProps) {
  const { progress, isScanning, error, startEnrollment } = useEnrollment();

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogHeader>
        <DialogTitle>Đăng ký khuôn mặt - {studentName}</DialogTitle>
      </DialogHeader>
      <div className="space-y-4">
        {error && <p className="text-sm text-red-500">{error}</p>}
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div className="bg-blue-600 h-2 rounded-full transition-all" style={{ width: `${progress}%` }} />
        </div>
        <p className="text-sm text-gray-500 text-center">{progress}% hoàn thành</p>
        <div className="flex gap-2 justify-end">
          <Button variant="outline" onClick={onClose} disabled={isScanning}>Hủy</Button>
          <Button onClick={() => startEnrollment(studentId)} disabled={isScanning}>
            {isScanning ? "Đang quét..." : "Bắt đầu quét"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
