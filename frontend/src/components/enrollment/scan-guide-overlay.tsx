export default function ScanGuideOverlay() {
  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
      <div className="border-4 border-blue-400 rounded-full w-48 h-48 opacity-70 animate-pulse" />
      <p className="absolute bottom-4 text-white text-sm bg-black/50 px-3 py-1 rounded-full">
        Giữ nguyên khuôn mặt trong khung
      </p>
    </div>
  );
}
