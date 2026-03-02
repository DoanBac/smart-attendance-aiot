"use client";
import { useAuthStore } from "@/store/auth-store";

export default function Navbar() {
  const { user, logout } = useAuthStore();
  return (
    <header className="h-16 border-b bg-white flex items-center justify-between px-6">
      <h1 className="text-lg font-semibold text-blue-600">AIoT Smart Attendance</h1>
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-600">{user?.full_name}</span>
        <button onClick={logout} className="text-sm text-red-500 hover:underline">
          Log Out
        </button>
      </div>
    </header>
  );
}
