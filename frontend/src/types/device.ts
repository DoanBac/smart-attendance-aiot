export interface Device {
  id: string;
  device_id: string;
  name: string;
  location: string;
  status: "online" | "offline";
  last_seen: string;
  ip_address: string;
}
