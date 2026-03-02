import { Device } from "@/types/device";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function DeviceStatusCard({ device }: { device: Device }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{device.name}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Trạng thái</span>
            <Badge variant={device.status === "online" ? "success" : "destructive"}>
              {device.status === "online" ? "Online" : "Offline"}
            </Badge>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Vị trí</span>
            <span>{device.location}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">IP</span>
            <span>{device.ip_address}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
