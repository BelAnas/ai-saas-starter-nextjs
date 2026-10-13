import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shopdesk AI",
  description: "A writing assistant for small online shops: product descriptions, customer replies and FAQ entries.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
