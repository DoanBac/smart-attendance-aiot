"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
	{ href: "/dashboard", label: "Dashboard" },
	{ href: "/dashboard/attendance", label: "Điểm danh" },
	{ href: "/dashboard/students", label: "Sinh viên" },
	{ href: "/dashboard/devices", label: "Thiết bị" },
	{ href: "/dashboard/reports", label: "Báo cáo" },
];

export default function Sidebar() {
	const pathname = usePathname();
	return (
		<aside className="w-64 border-r bg-white flex flex-col">
			<nav className="flex-1 p-4 space-y-1">
				{links.map((link) => (
					<Link
						key={link.href}
						href={link.href}
						className={`block px-4 py-2 rounded-md text-sm font-medium transition-colors ${
							pathname === link.href
								? "bg-blue-50 text-blue-600"
								: "text-gray-600 hover:bg-gray-100"
						}`}
					>
						{link.label}
					</Link>
				))}
			</nav>
		</aside>
	);
}
