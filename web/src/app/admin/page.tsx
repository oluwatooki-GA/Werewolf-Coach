import type { Metadata } from "next";
import { AdminBoard } from "@/components/AdminBoard";

export const metadata: Metadata = { title: "Admin", robots: { index: false } };

export default function AdminPage() {
  return <AdminBoard />;
}
