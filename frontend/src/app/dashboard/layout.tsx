"use client";

import dynamic from "next/dynamic";
import { TopBar } from "@/components/top-bar";

const AppSidebar = dynamic(() => import("@/components/app-sidebar").then((m) => m.AppSidebar), {
  ssr: false,
});

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-sidebar">
      <AppSidebar />
      <div className="relative flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <div className="flex-1 overflow-hidden px-2.5 pb-2.5">
          <main className="flex h-full flex-col overflow-hidden rounded-lg bg-background">
            <div className="flex flex-1 flex-col gap-4 overflow-auto p-4 md:p-6 lg:p-8">
              {children}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
