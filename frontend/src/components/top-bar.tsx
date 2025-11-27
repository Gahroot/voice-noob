"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fetchAgents } from "@/lib/api/agents";
import { listPhoneNumbers } from "@/lib/api/phone-numbers";
import { Bot, FolderOpen, Calendar, Phone, Users } from "lucide-react";

interface StatItemProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number | undefined;
  isLoading: boolean;
}

function StatItem({ icon: Icon, label, value, isLoading }: StatItemProps) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground">{isLoading ? "–" : (value ?? 0)}</span>
    </div>
  );
}

export function TopBar() {
  // Fetch agents count
  const { data: agents, isLoading: agentsLoading } = useQuery({
    queryKey: ["agents-count"],
    queryFn: fetchAgents,
    staleTime: 30000,
  });

  // Fetch workspaces count
  const { data: workspaces, isLoading: workspacesLoading } = useQuery({
    queryKey: ["workspaces-count"],
    queryFn: async () => {
      const response = await api.get("/api/v1/workspaces");
      return response.data;
    },
    staleTime: 30000,
  });

  // Fetch appointments count
  const { data: appointments, isLoading: appointmentsLoading } = useQuery({
    queryKey: ["appointments-count"],
    queryFn: async () => {
      const response = await api.get("/api/v1/crm/appointments");
      return response.data;
    },
    staleTime: 30000,
  });

  // Fetch phone numbers count
  const { data: phoneNumbersData, isLoading: phoneNumbersLoading } = useQuery({
    queryKey: ["phone-numbers-count"],
    queryFn: () => listPhoneNumbers(),
    staleTime: 30000,
  });

  // Fetch CRM contacts count
  const { data: contacts, isLoading: contactsLoading } = useQuery({
    queryKey: ["contacts-count"],
    queryFn: async () => {
      const response = await api.get("/api/v1/crm/contacts");
      return response.data;
    },
    staleTime: 30000,
  });

  return (
    <div className="flex h-12 items-center justify-end gap-6 bg-sidebar px-4">
      <StatItem icon={Bot} label="Agents" value={agents?.length} isLoading={agentsLoading} />
      <StatItem
        icon={FolderOpen}
        label="Workspaces"
        value={workspaces?.length}
        isLoading={workspacesLoading}
      />
      <StatItem
        icon={Calendar}
        label="Appointments"
        value={appointments?.length}
        isLoading={appointmentsLoading}
      />
      <StatItem
        icon={Phone}
        label="Phone Numbers"
        value={phoneNumbersData?.total}
        isLoading={phoneNumbersLoading}
      />
      <StatItem
        icon={Users}
        label="Contacts"
        value={contacts?.length}
        isLoading={contactsLoading}
      />
    </div>
  );
}
