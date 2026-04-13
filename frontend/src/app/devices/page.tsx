"use client";
import { useEffect, useState } from "react";
import { getApiBase, apiFetch } from "@/lib/api";
import { Monitor, Wifi, WifiOff, RefreshCw, Copy, ExternalLink, Zap, Check, X, Pencil } from "lucide-react";

interface Device {
  id: number;
  device_token: string;
  device_name: string | null;
  location: string | null;
  class_id: string | null;
  last_heartbeat: string | null;
  status: string;
  firmware_version: string | null;
  esp8266_url: string | null;
}

interface ClassOption {
  id: string;
  class_code: string;
  class_name: string;
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<Device[]>([]);
  const [classes, setClasses] = useState<ClassOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showRegister, setShowRegister] = useState(false);
  const [form, setForm] = useState({ device_name: "", location: "", class_id: "" });
  const [newToken, setNewToken] = useState("");
  // ESP8266 inline edit: deviceId → draft URL
  const [esp8266Edit, setEsp8266Edit] = useState<Record<number, string>>({});
  const [esp8266Saving, setEsp8266Saving] = useState<number | null>(null);

  // Edit device modal
  const [editDevice, setEditDevice] = useState<Device | null>(null);
  const [editForm, setEditForm] = useState({ device_name: "", location: "", class_id: "" });
  const [editSaving, setEditSaving] = useState(false);

  const base = getApiBase();
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : "";

  const fetchDevices = (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    fetch(`${base}/api/devices/`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json()).then(setDevices).catch(() => setDevices([]))
      .finally(() => { setLoading(false); setRefreshing(false); });
  };

  const classLabel = (classId: string | null) => {
    if (!classId) return "—";
    const c = classes.find((x) => x.id === classId);
    return c ? `${c.class_name} (${c.class_code})` : `Class #${classId}`;
  };

  useEffect(() => {
    fetchDevices();
    apiFetch("/api/classes/")
      .then((r) => r.json())
      .then((d) => setClasses(Array.isArray(d) ? d : d.items ?? []))
      .catch(() => setClasses([]));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    const res = await fetch(`${base}/api/devices/register`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, class_id: form.class_id || null }),
    });
    const data = await res.json();
    setNewToken(data.device_token || "");
    fetchDevices();
  };

  // Fix: DB stores naive UTC, API returns no "Z" suffix → JS parses as local time → 7h drift
  const isOnline = (heartbeat: string | null) => {
    if (!heartbeat) return false;
    const utcTs = heartbeat.endsWith("Z") || heartbeat.includes("+") ? heartbeat : heartbeat + "Z";
    return (Date.now() - new Date(utcTs).getTime()) < 90_000; // 90 s
  };

  const saveEsp8266 = async (deviceId: number) => {
    setEsp8266Saving(deviceId);
    try {
      const url = esp8266Edit[deviceId] ?? "";
      await fetch(`${base}/api/devices/${deviceId}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ esp8266_url: url || null }),
      });
      fetchDevices();
      setEsp8266Edit((e) => { const n = { ...e }; delete n[deviceId]; return n; });
    } finally {
      setEsp8266Saving(null);
    }
  };

  const openEditDevice = (d: Device) => {
    setEditDevice(d);
    setEditForm({ device_name: d.device_name ?? "", location: d.location ?? "", class_id: d.class_id ? String(d.class_id) : "" });
  };

  const handleEditDevice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editDevice) return;
    setEditSaving(true);
    try {
      await fetch(`${base}/api/devices/${editDevice.id}`, {
        method: "PATCH",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          device_name: editForm.device_name.trim() || null,
          location: editForm.location.trim() || null,
          class_id: editForm.class_id || null,
        }),
      });
      setEditDevice(null);
      fetchDevices();
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-800">Edge Device Management</h1>
        <div className="flex gap-3">
          <button onClick={() => fetchDevices(true)} disabled={refreshing} className="flex items-center gap-2 border border-gray-200 px-3 py-2 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-60">
            <RefreshCw className={`w-4 h-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
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
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Device Name *</label>
              <input required
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Pi - Room 201"
                value={form.device_name}
                onChange={(e) => setForm((f) => ({ ...f, device_name: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Location</label>
              <input
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="Room 201, Building A"
                value={form.location}
                onChange={(e) => setForm((f) => ({ ...f, location: e.target.value }))}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Assigned Class</label>
              <select
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-700"
                value={form.class_id}
                onChange={(e) => setForm((f) => ({ ...f, class_id: e.target.value }))}
              >
                <option value="">— None —</option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>{c.class_name} ({c.class_code})</option>
                ))}
              </select>
            </div>
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
                  <div className="flex items-center gap-2">
                    <button onClick={() => openEditDevice(d)}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors" title="Edit device">
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
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
                </div>
                <div className="text-xs text-gray-500 space-y-1">
                  <p><span className="text-gray-400">Class:</span> <span className="font-medium text-gray-700">{classLabel(d.class_id)}</span></p>
                  <p><span className="text-gray-400">Firmware:</span> {d.firmware_version || "—"}</p>
                  <p><span className="text-gray-400">Last heartbeat:</span> {d.last_heartbeat
                    ? new Date(
                        d.last_heartbeat.endsWith("Z") || d.last_heartbeat.includes("+")
                          ? d.last_heartbeat
                          : d.last_heartbeat + "Z"
                      ).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "medium" })
                    : "Never"}</p>
                </div>

                {/* ── ESP8266 Door Lock ── */}
                <div className="mt-3 pt-3 border-t border-gray-100">
                  <p className="text-xs font-medium text-gray-500 mb-1.5 flex items-center gap-1">
                    <Zap className="w-3 h-3 text-yellow-500" /> ESP8266 Door Unlock URL
                  </p>
                  {esp8266Edit[d.id] !== undefined ? (
                    <div className="flex gap-1.5">
                      <input
                        autoFocus
                        className="flex-1 text-xs px-2 py-1.5 border border-blue-300 rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-400"
                        placeholder="http://192.168.1.x/open"
                        value={esp8266Edit[d.id]}
                        onChange={(e) => setEsp8266Edit((prev) => ({ ...prev, [d.id]: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === "Enter") saveEsp8266(d.id); if (e.key === "Escape") setEsp8266Edit((prev) => { const n = { ...prev }; delete n[d.id]; return n; }); }}
                      />
                      <button
                        onClick={() => saveEsp8266(d.id)}
                        disabled={esp8266Saving === d.id}
                        className="p-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-60"
                      >
                        <Check className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setEsp8266Edit((prev) => { const n = { ...prev }; delete n[d.id]; return n; })}
                        className="p-1.5 bg-gray-100 text-gray-500 rounded-lg hover:bg-gray-200"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setEsp8266Edit((prev) => ({ ...prev, [d.id]: d.esp8266_url ?? "" }))}
                      className={`text-xs px-2 py-1.5 rounded-lg border w-full text-left truncate transition-colors ${d.esp8266_url ? "border-yellow-300 bg-yellow-50 text-yellow-800 hover:bg-yellow-100" : "border-dashed border-gray-200 text-gray-400 hover:bg-gray-50"}`}
                    >
                      {d.esp8266_url || "Click to configure…"}
                    </button>
                  )}
                </div>

                {/* ── Kiosk buttons (only when device has a class) ── */}
                {d.class_id && (() => {
                  const classCode = classes.find((c) => c.id === d.class_id)?.class_code ?? String(d.class_id);
                  return (
                    <div className="mt-4 pt-3 border-t border-gray-100 flex gap-2">
                      <button
                        onClick={() => {
                          localStorage.setItem(`kiosk_token_${classCode}`, d.device_token);
                          if (d.esp8266_url) {
                            localStorage.setItem(`kiosk_esp_${classCode}`, d.esp8266_url);
                          } else {
                            localStorage.removeItem(`kiosk_esp_${classCode}`);
                          }
                          window.open(`/kiosk/${classCode}`, "_blank");
                        }}
                        className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-blue-50 hover:bg-blue-100 text-blue-700 rounded-lg text-xs font-medium transition-colors"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        Open Kiosk
                      </button>
                      <button
                        onClick={() => navigator.clipboard.writeText(`${window.location.origin}/kiosk/${classCode}`)}
                        title="Copy Kiosk URL"
                        className="p-2 bg-gray-50 hover:bg-gray-100 text-gray-500 rounded-lg transition-colors"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  );
                })()}
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

      {/* Edit Device Modal */}
      {editDevice && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-sm p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-gray-800">Edit Device</h2>
              <button onClick={() => setEditDevice(null)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
            </div>
            <form onSubmit={handleEditDevice} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Device Name</label>
                <input
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Pi - Room 201"
                  value={editForm.device_name}
                  onChange={(e) => setEditForm((f) => ({ ...f, device_name: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Location / Room</label>
                <input
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Room 201, Building A"
                  value={editForm.location}
                  onChange={(e) => setEditForm((f) => ({ ...f, location: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Assigned Class</label>
                <select
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-700"
                  value={editForm.class_id}
                  onChange={(e) => setEditForm((f) => ({ ...f, class_id: e.target.value }))}
                >
                  <option value="">— None —</option>
                  {classes.map((c) => (
                    <option key={c.id} value={c.id}>{c.class_name} ({c.class_code})</option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3 pt-1">
                <button type="submit" disabled={editSaving}
                  className="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-60">
                  {editSaving ? "Saving..." : "Save Changes"}
                </button>
                <button type="button" onClick={() => setEditDevice(null)} className="flex-1 border border-gray-200 py-2 rounded-lg text-sm hover:bg-gray-50">Cancel</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
