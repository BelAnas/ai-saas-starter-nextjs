import { redirect } from "next/navigation";
import { AuthForm } from "@/components/AuthForm";
import { getCurrentUser } from "@/lib/server";

export default async function Page() {
  if (await getCurrentUser()) redirect("/app");
  return <AuthForm mode="login" />;
}
