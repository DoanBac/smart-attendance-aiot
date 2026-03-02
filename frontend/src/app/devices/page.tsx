"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";
import { Monitor, Wifi, WifiOff, RefreshCw, Copy } from "lucide-react";

interface Device {
  id: number;
  device_token: string;
  device_name: string | null;
  location: string | null;
  class_id: number | null;
  last_heartbeat: string | null;
  status: string;
  firmware_version: string | null;
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);
  const [form, setForm] = useState({ device_name: "", location: "", class_id: "" });
  const [newToken, setNewToken] = useState("");

  const base = getApiBase();
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  const fetchDevices = () => {
    fetch(`${base}/api/devices/`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json()).then(setDevices).catch(() => setDevices([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchDevices(); }, []);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await fetch(`${base}/api/devices/register`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, class_id: form.class_id ? parseInt(form.class_id) : null }),
    });
    const data = await res.json();
    setNewToken(data.device_token || "");
    fetchDevices();
  };

  const isOnline = (heartbeat: string | null) => {
    if (!heartbeat) return false;
    return (Date.now() - new Date(heartbeat).getTime()) < 60000; // 1 min
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Edge Device Management</h1>
        <div className="flex gap-3">
          <button onClick={fetchDevices} className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm hover:bg-gray-50">
            <RefreshCw className="w-4 h-4" /> Refresh
          </button>
          <button
            onClick={() => setShowRegister(!showRegister)}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2.5 rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            + Register Device
          </button>
        </div>
      </div>

      {/* Register form */}
      {showRegister && (
        <form onSubmit={handleRegister} className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 mb-6 space-y-4">
          <h3 className="font-semibold text-gray-700">Register New Raspberry Pi Device</h3>
          <div className="grid grid-cols-3 gap-4">
            {[
              { name: "device_name", label: "Device Name", required: true },
              { name: "location", label: "Location" },
              { name: "class_id", label: "Class ID" },
            ].map(({ name, label, required }) => (
              <div key={name}>
                <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
                <input
                  required={required}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={(form as Record<string, string>)[name]}
                  onChange={(e) => setForm((f) => ({ ...f, [name]: e.target.value }))}
                />
              </div>
            ))}
          </div>
          <button type="submit" className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
            Generate Device Token
          </button>

          {newToken && (
            <div className="bg-green-50 border border-green-200 rounded-lg p-4">
              <p className="text-sm font-medium text-green-700 mb-2">✅ Device Token created — Copy to edge/config/device.env:</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 bg-green-100 px-3 py-2 rounded text-sm font-mono text-green-800 break-all">
                  DEVICE_TOKEN={newToken}
                </code>
                <button
                  onClick={() => navigator.clipboard.writeText(newToken)}
                  className="p-2 hover:bg-green-100 rounded"
                  title="Copy"
                >
                  <Copy className="w-4 h-4 text-green-600" />
                </button>
              </div>
            </div>
          )}
        </form>
      )}

      {/* Devices grid */}
      {loading ? (
        <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" /></div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {devices.map((d) => {
            const online = isOnline(d.last_heartbeat);
            return (
              <div key={d.id} className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${online ? "bg-green-50" : "bg-gray-100"}`}>
                      <Monitor className={`w-5 h-5 ${online ? "text-green-600" : "text-gray-400"}`} />
                    </div>
                    <div>
                      <p className="font-semibold text-gray-800">{d.device_name || `Device #${d.id}`}</p>
                      <p className="text-xs text-gray-400">{d.location || "No location set"}</p>
                    </div>
                  </div>
                  {online ? (
                    <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-2 py-1 rounded-full">
                      <Wifi className="w-3 h-3" /> Online
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded-full">
                      <WifiOff className="w-3 h-3" /> Offline
                    </span>
                  )}
                </div>
                <div className="text-xs text-gray-400 space-y-1">
                  <p>🎓 Lớp: {d.class_id || "—"}</p>
                  <p>🔧 Firmware: {d.firmware_version || "—"}</p>
                  <p>💓 Heartbeat: {d.last_heartbeat ? new Date(d.last_heartbeat).toLocaleString("en-US") : "Never"}</p>
                </div>
              </div>
            );
          })}
          {devices.length === 0 && (
            <div className="col-span-3 text-center py-12 text-gray-400">
              No devices registered yet.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
