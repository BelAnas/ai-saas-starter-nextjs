import { redirect } from "next/navigation";
import { ChatWorkspace } from "@/components/ChatWorkspace";
import { getCurrentUser } from "@/lib/server";

export default async function Page() {
  // Checked on the server, so a signed-out visitor never receives the app's HTML.
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  return <ChatWorkspace user={user} />;
}
