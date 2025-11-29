import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Voice Agent",
  description: "AI-powered voice assistant",
};

export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-transparent">{children}</body>
    </html>
  );
}
