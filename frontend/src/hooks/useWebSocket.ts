import { useEffect, useRef } from "react";
import { useAttendanceStore } from "@/store/attendance-store";

export function useWebSocket(deviceId?: string) {
  const ws = useRef<WebSocket | null>(null);
  const addRealtimeRecord = useAttendanceStore((s) => s.addRealtimeRecord);

  useEffect(() => {
    const url = deviceId
      ? `ws://localhost:8000/ws/attendance/${deviceId}`
      : `ws://localhost:8000/ws/attendance`;

    ws.current = new WebSocket(url);

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === "attendance") {
        addRealtimeRecord(data.payload);
      }
    };

    return () => {
      ws.current?.close();
    };
  }, [deviceId, addRealtimeRecord]);

  return ws;
}
