interface ScanProgressProps {
  progress: number;
  total?: number;
}

export default function ScanProgress({ progress, total = 100 }: ScanProgressProps) {
  const pct = Math.round((progress / total) * 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>Tiến trình</span>
        <span>{pct}%</span>
      </div>
      <div className="w-full bg-gray-200 rounded-full h-2">
        <div className="bg-blue-600 h-2 rounded-full transition-all duration-300" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
