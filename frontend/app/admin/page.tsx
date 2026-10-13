import { redirect } from "next/navigation";
import { AdminDashboard } from "@/components/AdminDashboard";
import { getCurrentUser } from "@/lib/server";

export default async function Page() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  // This only decides what to show. The API checks the role again on every admin request.
  if (user.role !== "admin") redirect("/app");
  return <AdminDashboard user={user} />;
}
