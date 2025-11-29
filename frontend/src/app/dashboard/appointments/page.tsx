"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Plus,
  Phone,
  Calendar,
  Clock,
  Loader2,
  AlertCircle,
  X,
  User,
  FolderOpen,
} from "lucide-react";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { toast } from "sonner";
import Link from "next/link";

interface Workspace {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
}

interface Appointment {
  id: number;
  contact_id: number;
  workspace_id: string | null;
  scheduled_at: string;
  duration_minutes: number;
  status: string;
  service_type: string | null;
  notes: string | null;
  created_by_agent: string | null;
  contact_name: string | null;
  contact_phone: string | null;
}

interface Contact {
  id: number;
  first_name: string;
  last_name: string | null;
  phone_number: string;
}

type AppointmentFormData = {
  contact_id: number | null;
  scheduled_at: string;
  duration_minutes: number;
  service_type: string;
  notes: string;
  status: string;
  workspace_id: string;
};

const emptyFormData: AppointmentFormData = {
  contact_id: null,
  scheduled_at: "",
  duration_minutes: 30,
  service_type: "",
  notes: "",
  status: "scheduled",
  workspace_id: "",
};

export default function AppointmentsPage() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"add" | "edit" | "view">("add");
  const [selectedAppointment, setSelectedAppointment] = useState<Appointment | null>(null);
  const [formData, setFormData] = useState<AppointmentFormData>(emptyFormData);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("all");

  // Fetch workspaces
  const { data: workspaces = [] } = useQuery<Workspace[]>({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const response = await api.get("/api/v1/workspaces");
      return response.data;
    },
  });

  const {
    data: appointments = [],
    isLoading,
    error,
  } = useQuery<Appointment[]>({
    queryKey: ["appointments", statusFilter, selectedWorkspaceId],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.append("status", statusFilter);
      if (selectedWorkspaceId !== "all") params.append("workspace_id", selectedWorkspaceId);
      const queryString = params.toString() ? `?${params.toString()}` : "";
      const response = await api.get(`/api/v1/crm/appointments${queryString}`);
      return response.data;
    },
  });

  const { data: contacts = [] } = useQuery<Contact[]>({
    queryKey: ["contacts", selectedWorkspaceId],
    queryFn: async () => {
      const url =
        selectedWorkspaceId !== "all"
          ? `/api/v1/crm/contacts?workspace_id=${selectedWorkspaceId}`
          : "/api/v1/crm/contacts";
      const response = await api.get(url);
      return response.data;
    },
  });

  const createAppointmentMutation = useMutation({
    mutationFn: async (data: AppointmentFormData) => {
      const response = await api.post("/api/v1/crm/appointments", {
        contact_id: data.contact_id,
        scheduled_at: data.scheduled_at,
        duration_minutes: data.duration_minutes,
        service_type: data.service_type ?? null,
        notes: data.notes ?? null,
      });
      return response.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
      toast.success("Appointment created successfully");
      closeModal();
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to create appointment");
    },
  });

  const updateAppointmentMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number; data: Partial<AppointmentFormData> }) => {
      const response = await api.put(`/api/v1/crm/appointments/${id}`, {
        scheduled_at: data.scheduled_at,
        duration_minutes: data.duration_minutes,
        status: data.status,
        service_type: data.service_type ?? null,
        notes: data.notes ?? null,
      });
      return response.data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
      toast.success("Appointment updated successfully");
      closeModal();
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to update appointment");
    },
  });

  const deleteAppointmentMutation = useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/api/v1/crm/appointments/${id}`);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["appointments"] });
      toast.success("Appointment deleted successfully");
      closeModal();
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to delete appointment");
    },
  });

  const openAddModal = () => {
    // Pre-fill workspace_id if a workspace is selected
    const defaultWorkspaceId =
      selectedWorkspaceId !== "all" ? selectedWorkspaceId : (workspaces[0]?.id ?? "");
    setFormData({ ...emptyFormData, workspace_id: defaultWorkspaceId });
    setSelectedAppointment(null);
    setModalMode("add");
    setIsModalOpen(true);
  };

  const openViewModal = (appointment: Appointment) => {
    setSelectedAppointment(appointment);
    setFormData({
      contact_id: appointment.contact_id,
      scheduled_at: appointment.scheduled_at.slice(0, 16),
      duration_minutes: appointment.duration_minutes,
      service_type: appointment.service_type ?? "",
      notes: appointment.notes ?? "",
      status: appointment.status,
      workspace_id: appointment.workspace_id ?? "",
    });
    setModalMode("view");
    setIsModalOpen(true);
  };

  const switchToEditMode = () => {
    setModalMode("edit");
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setSelectedAppointment(null);
    setFormData(emptyFormData);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (modalMode === "add") {
      if (!formData.contact_id) {
        toast.error("Please select a contact");
        return;
      }
      createAppointmentMutation.mutate(formData);
    } else if (modalMode === "edit" && selectedAppointment) {
      updateAppointmentMutation.mutate({ id: selectedAppointment.id, data: formData });
    }
  };

  const handleDelete = () => {
    setIsDeleteDialogOpen(true);
  };

  const confirmDelete = () => {
    if (selectedAppointment) {
      deleteAppointmentMutation.mutate(selectedAppointment.id);
    }
    setIsDeleteDialogOpen(false);
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      scheduled: "bg-blue-100 text-blue-800",
      completed: "bg-green-100 text-green-800",
      cancelled: "bg-red-100 text-red-800",
      no_show: "bg-gray-100 text-gray-800",
    };
    return colors[status] ?? "bg-gray-100 text-gray-800";
  };

  const formatDateTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const isSubmitting = createAppointmentMutation.isPending || updateAppointmentMutation.isPending;

  const scheduledCount = appointments.filter((a) => a.status === "scheduled").length;
  const completedCount = appointments.filter((a) => a.status === "completed").length;
  const cancelledCount = appointments.filter((a) => a.status === "cancelled").length;

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">Appointments</h1>
          <p className="text-sm text-muted-foreground">Manage your scheduled appointments</p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <AlertCircle className="mb-4 h-12 w-12 text-destructive" />
            <h3 className="mb-2 text-lg font-semibold">Failed to load appointments</h3>
            <p className="text-sm text-muted-foreground">
              {error instanceof Error ? error.message : "An error occurred"}
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Appointments</h1>
          <p className="text-sm text-muted-foreground">Manage your scheduled appointments</p>
        </div>
        <div className="flex items-center gap-3">
          {workspaces.length > 0 ? (
            <Select
              value={selectedWorkspaceId}
              onValueChange={(value) => {
                setSelectedWorkspaceId(value);
                const wsName =
                  value === "all"
                    ? "All Workspaces"
                    : workspaces.find((ws) => ws.id === value)?.name;
                toast.info(`Switched to ${wsName}`);
              }}
            >
              <SelectTrigger className="h-8 w-[180px] text-sm">
                <FolderOpen className="mr-2 h-3.5 w-3.5" />
                <SelectValue placeholder="All Workspaces" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Workspaces</SelectItem>
                {workspaces.map((ws) => (
                  <SelectItem key={ws.id} value={ws.id}>
                    {ws.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Link
              href="/dashboard/workspaces"
              className="text-sm text-muted-foreground hover:text-foreground"
            >
              Create a workspace
            </Link>
          )}
          <Button size="sm" onClick={openAddModal} disabled={contacts.length === 0}>
            <Plus className="mr-2 h-4 w-4" />
            New Appointment
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-3 md:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Scheduled</p>
                <p className="text-lg font-semibold">{scheduledCount}</p>
              </div>
              <Calendar className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Completed</p>
                <p className="text-lg font-semibold">{completedCount}</p>
              </div>
              <Clock className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Cancelled</p>
                <p className="text-lg font-semibold">{cancelledCount}</p>
              </div>
              <X className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Filter:</span>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="h-8 w-[140px] text-xs">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="scheduled">Scheduled</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
            <SelectItem value="no_show">No Show</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Appointments List */}
      {isLoading ? (
        <Card>
          <CardContent className="flex items-center justify-center py-16">
            <p className="text-muted-foreground">Loading appointments...</p>
          </CardContent>
        </Card>
      ) : contacts.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <User className="mb-4 h-16 w-16 text-muted-foreground/50" />
            <h3 className="mb-2 text-lg font-semibold">No contacts available</h3>
            <p className="mb-4 max-w-sm text-center text-sm text-muted-foreground">
              You need to add contacts before creating appointments
            </p>
            <Button variant="outline" asChild>
              <a href="/dashboard/crm">Go to CRM</a>
            </Button>
          </CardContent>
        </Card>
      ) : appointments.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Calendar className="mb-4 h-16 w-16 text-muted-foreground/50" />
            <h3 className="mb-2 text-lg font-semibold">No appointments yet</h3>
            <p className="mb-4 max-w-sm text-center text-sm text-muted-foreground">
              Create appointments manually or they&apos;ll be created automatically from voice agent
              calls
            </p>
            <Button onClick={openAddModal}>
              <Plus className="mr-2 h-4 w-4" />
              Create Your First Appointment
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {appointments.map((appointment) => (
            <Card
              key={appointment.id}
              className="group cursor-pointer transition-all hover:border-primary/50"
              onClick={() => openViewModal(appointment)}
            >
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5 overflow-hidden">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10">
                      <Calendar className="h-4 w-4 text-primary" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="truncate text-sm font-medium">
                        {appointment.contact_name ?? "Unknown Contact"}
                      </h3>
                      <p className="truncate text-xs text-muted-foreground">
                        {formatDateTime(appointment.scheduled_at)}
                      </p>
                    </div>
                  </div>
                  <span
                    className={`inline-flex h-5 shrink-0 items-center rounded-full px-1.5 text-[10px] font-medium ${getStatusColor(appointment.status)}`}
                  >
                    {appointment.status.replace("_", " ")}
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  {appointment.contact_phone && (
                    <div className="flex items-center gap-1">
                      <Phone className="h-3 w-3" />
                      <span>{appointment.contact_phone}</span>
                    </div>
                  )}
                  <div className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>{appointment.duration_minutes} min</span>
                  </div>
                </div>

                {appointment.service_type && (
                  <div className="mt-2.5 border-t border-border/50 pt-2.5 text-xs text-muted-foreground">
                    {appointment.service_type}
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Appointment Modal */}
      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle className="flex items-center justify-between">
              {modalMode === "add" && "New Appointment"}
              {modalMode === "edit" && "Edit Appointment"}
              {modalMode === "view" && "Appointment Details"}
            </DialogTitle>
            <DialogDescription>
              {modalMode === "add" && "Schedule a new appointment."}
              {modalMode === "edit" && "Update the appointment details."}
              {modalMode === "view" && "View and manage appointment details."}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit}>
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="contact_id">Contact *</Label>
                <Select
                  value={formData.contact_id?.toString() ?? ""}
                  onValueChange={(value) =>
                    setFormData({ ...formData, contact_id: parseInt(value) })
                  }
                  disabled={modalMode !== "add"}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a contact" />
                  </SelectTrigger>
                  <SelectContent>
                    {contacts.map((contact) => (
                      <SelectItem key={contact.id} value={contact.id.toString()}>
                        {contact.first_name} {contact.last_name} - {contact.phone_number}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="scheduled_at">Date & Time *</Label>
                <Input
                  id="scheduled_at"
                  type="datetime-local"
                  value={formData.scheduled_at}
                  onChange={(e) => setFormData({ ...formData, scheduled_at: e.target.value })}
                  disabled={modalMode === "view"}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="duration_minutes" className="flex items-center gap-1">
                  Duration (minutes)
                  <InfoTooltip content="How long the appointment will last. Choose a duration that fits the type of service or meeting you're scheduling." />
                </Label>
                <Select
                  value={formData.duration_minutes.toString()}
                  onValueChange={(value) =>
                    setFormData({ ...formData, duration_minutes: parseInt(value) })
                  }
                  disabled={modalMode === "view"}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select duration" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15 minutes</SelectItem>
                    <SelectItem value="30">30 minutes</SelectItem>
                    <SelectItem value="45">45 minutes</SelectItem>
                    <SelectItem value="60">1 hour</SelectItem>
                    <SelectItem value="90">1.5 hours</SelectItem>
                    <SelectItem value="120">2 hours</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {(modalMode === "edit" || modalMode === "view") && (
                <div className="space-y-2">
                  <Label htmlFor="status" className="flex items-center gap-1">
                    Status
                    <InfoTooltip content="Track the appointment state. Scheduled = upcoming, Completed = done, Cancelled = called off, No Show = contact didn't attend." />
                  </Label>
                  <Select
                    value={formData.status}
                    onValueChange={(value) => setFormData({ ...formData, status: value })}
                    disabled={modalMode === "view"}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Select status" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="scheduled">Scheduled</SelectItem>
                      <SelectItem value="completed">Completed</SelectItem>
                      <SelectItem value="cancelled">Cancelled</SelectItem>
                      <SelectItem value="no_show">No Show</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="service_type" className="flex items-center gap-1">
                  Service Type
                  <InfoTooltip content="Describe what kind of appointment this is. Examples: Consultation, Follow-up call, Product demo, Support session." />
                </Label>
                <Input
                  id="service_type"
                  value={formData.service_type}
                  onChange={(e) => setFormData({ ...formData, service_type: e.target.value })}
                  disabled={modalMode === "view"}
                  placeholder="e.g., Consultation, Follow-up, Demo"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="notes">Notes</Label>
                <Textarea
                  id="notes"
                  value={formData.notes}
                  onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
                  disabled={modalMode === "view"}
                  rows={3}
                />
              </div>

              {modalMode === "view" && selectedAppointment?.created_by_agent && (
                <div className="rounded-md bg-muted p-3">
                  <p className="text-sm text-muted-foreground">
                    Created by voice agent: {selectedAppointment.created_by_agent}
                  </p>
                </div>
              )}
            </div>

            <DialogFooter className="gap-2">
              {modalMode === "view" && (
                <>
                  <Button
                    type="button"
                    variant="destructive"
                    onClick={handleDelete}
                    disabled={deleteAppointmentMutation.isPending}
                  >
                    {deleteAppointmentMutation.isPending ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <X className="mr-2 h-4 w-4" />
                    )}
                    Delete
                  </Button>
                  <Button type="button" onClick={switchToEditMode}>
                    Edit Appointment
                  </Button>
                </>
              )}
              {(modalMode === "add" || modalMode === "edit") && (
                <>
                  <Button type="button" variant="outline" onClick={closeModal}>
                    Cancel
                  </Button>
                  <Button type="submit" disabled={isSubmitting}>
                    {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {modalMode === "add" ? "Create Appointment" : "Save Changes"}
                  </Button>
                </>
              )}
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Appointment</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this appointment
              {selectedAppointment?.contact_name ? ` with ${selectedAppointment.contact_name}` : ""}
              ? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={confirmDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
