import { AdminLayout } from "@/components/admin/AdminLayout";
import { AdminAuthGuard } from "@/components/admin/AdminAuthGuard";

export default function AdminPage() {
  return (
    <AdminAuthGuard>
      <AdminLayout />
    </AdminAuthGuard>
  );
}
