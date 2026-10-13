import { redirect } from "next/navigation";
import { AccountView } from "@/components/AccountView";
import { getCurrentUser } from "@/lib/server";

export default async function Page() {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return <AccountView user={user} />;
}
