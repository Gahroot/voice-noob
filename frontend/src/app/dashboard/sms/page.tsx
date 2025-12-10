"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  MessageSquare,
  Send,
  Plus,
  Loader2,
  AlertCircle,
  Clock,
  CheckCheck,
  User,
  Phone,
  ArrowRight,
  Megaphone,
  Users,
  BarChart3,
  FolderOpen,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import {
  listConversations,
  listCampaigns,
  sendMessage,
  createCampaign,
  startCampaign,
  pauseCampaign,
  type SMSConversation,
  type SMSCampaign,
  type CreateCampaignRequest,
} from "@/lib/api/sms";
import { listPhoneNumbers, type PhoneNumber } from "@/lib/api/telephony";
import { fetchSettings } from "@/lib/api/settings";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";

interface Workspace {
  id: string;
  name: string;
  description: string | null;
  is_default: boolean;
}

interface Contact {
  id: number;
  first_name: string;
  last_name: string | null;
  phone_number: string;
}

export default function SMSPage() {
  const queryClient = useQueryClient();
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"conversations" | "campaigns">("conversations");
  const [isNewMessageOpen, setIsNewMessageOpen] = useState(false);
  const [isNewCampaignOpen, setIsNewCampaignOpen] = useState(false);
  const [newMessageData, setNewMessageData] = useState({
    to_number: "",
    from_number: "",
    body: "",
    provider: "telnyx",
  });
  const [newCampaignData, setNewCampaignData] = useState<CreateCampaignRequest>({
    name: "",
    description: "",
    from_phone_number: "",
    initial_message: "",
    ai_enabled: true,
    contact_ids: [],
  });
  const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);

  // Fetch workspaces
  const { data: workspaces = [] } = useQuery<Workspace[]>({
    queryKey: ["workspaces"],
    queryFn: async () => {
      const response = await api.get("/api/v1/workspaces");
      return response.data;
    },
  });

  // Set default workspace when loaded
  const activeWorkspaceId = selectedWorkspaceId ?? workspaces[0]?.id ?? "";

  // Fetch conversations
  const {
    data: conversations = [],
    isLoading: conversationsLoading,
    error: conversationsError,
  } = useQuery<SMSConversation[]>({
    queryKey: ["sms-conversations", activeWorkspaceId],
    queryFn: () => listConversations(activeWorkspaceId),
    enabled: !!activeWorkspaceId,
  });

  // Fetch campaigns
  const {
    data: campaigns = [],
    isLoading: campaignsLoading,
    error: campaignsError,
  } = useQuery<SMSCampaign[]>({
    queryKey: ["sms-campaigns", activeWorkspaceId],
    queryFn: () => listCampaigns(activeWorkspaceId),
    enabled: !!activeWorkspaceId,
  });

  // Fetch phone numbers (Telnyx + SlickText from settings)
  const { data: phoneNumbers = [] } = useQuery<PhoneNumber[]>({
    queryKey: ["phoneNumbers", activeWorkspaceId],
    queryFn: async () => {
      if (!activeWorkspaceId) return [];
      // Get Telnyx phone numbers
      const telnyxNumbers = await listPhoneNumbers("telnyx", activeWorkspaceId);
      // Get SlickText phone number from settings
      const settings = await fetchSettings(activeWorkspaceId);
      const allNumbers: PhoneNumber[] = [...telnyxNumbers];
      if (settings.slicktext_phone_number) {
        allNumbers.push({
          id: "slicktext-" + settings.slicktext_phone_number,
          phone_number: settings.slicktext_phone_number,
          friendly_name: "SlickText",
          provider: "slicktext",
          capabilities: { sms: true },
          assigned_agent_id: null,
        });
      }
      return allNumbers;
    },
    enabled: !!activeWorkspaceId,
  });

  // Fetch contacts for campaign creation
  const { data: contacts = [] } = useQuery<Contact[]>({
    queryKey: ["contacts", activeWorkspaceId],
    queryFn: async () => {
      const response = await api.get(`/api/v1/crm/contacts?workspace_id=${activeWorkspaceId}`);
      return response.data;
    },
    enabled: !!activeWorkspaceId && isNewCampaignOpen,
  });

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: async (data: typeof newMessageData) => {
      return sendMessage(data, activeWorkspaceId);
    },
    onSuccess: () => {
      toast.success("Message sent!");
      setIsNewMessageOpen(false);
      setNewMessageData({ to_number: "", from_number: "", body: "", provider: "telnyx" });
      void queryClient.invalidateQueries({ queryKey: ["sms-conversations"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to send message");
    },
  });

  // Create campaign mutation
  const createCampaignMutation = useMutation({
    mutationFn: async (data: CreateCampaignRequest) => {
      return createCampaign(data, activeWorkspaceId);
    },
    onSuccess: () => {
      toast.success("Campaign created!");
      setIsNewCampaignOpen(false);
      setNewCampaignData({
        name: "",
        description: "",
        from_phone_number: "",
        initial_message: "",
        ai_enabled: true,
        contact_ids: [],
      });
      setSelectedContactIds([]);
      void queryClient.invalidateQueries({ queryKey: ["sms-campaigns"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to create campaign");
    },
  });

  // Start/pause campaign mutations
  const startCampaignMutation = useMutation({
    mutationFn: startCampaign,
    onSuccess: () => {
      toast.success("Campaign started!");
      void queryClient.invalidateQueries({ queryKey: ["sms-campaigns"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to start campaign");
    },
  });

  const pauseCampaignMutation = useMutation({
    mutationFn: pauseCampaign,
    onSuccess: () => {
      toast.success("Campaign paused!");
      void queryClient.invalidateQueries({ queryKey: ["sms-campaigns"] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to pause campaign");
    },
  });

  const handleSendMessage = () => {
    if (!newMessageData.to_number || !newMessageData.from_number || !newMessageData.body) {
      toast.error("Please fill in all fields");
      return;
    }
    sendMessageMutation.mutate(newMessageData);
  };

  const handleCreateCampaign = () => {
    if (
      !newCampaignData.name ||
      !newCampaignData.from_phone_number ||
      !newCampaignData.initial_message
    ) {
      toast.error("Please fill in required fields");
      return;
    }
    createCampaignMutation.mutate({
      ...newCampaignData,
      contact_ids: selectedContactIds,
    });
  };

  const getStatusBadge = (status: string) => {
    const statusColors: Record<string, string> = {
      draft: "bg-gray-100 text-gray-800",
      scheduled: "bg-blue-100 text-blue-800",
      running: "bg-green-100 text-green-800",
      paused: "bg-yellow-100 text-yellow-800",
      completed: "bg-purple-100 text-purple-800",
      canceled: "bg-red-100 text-red-800",
    };
    return statusColors[status] ?? "bg-gray-100 text-gray-800";
  };

  const totalUnread = conversations.reduce((sum, c) => sum + (c.unread_count ?? 0), 0);

  if (!activeWorkspaceId && workspaces.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-xl font-semibold">SMS</h1>
          <p className="text-sm text-muted-foreground">Manage SMS conversations and campaigns</p>
        </div>
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-12">
            <FolderOpen className="mb-4 h-12 w-12 text-muted-foreground" />
            <h3 className="mb-2 text-lg font-semibold">No workspaces found</h3>
            <p className="text-sm text-muted-foreground">
              <Link href="/dashboard/workspaces" className="text-primary hover:underline">
                Create a workspace
              </Link>{" "}
              to start using SMS features.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">SMS</h1>
          <p className="text-sm text-muted-foreground">
            Manage conversations and lead qualification campaigns
          </p>
        </div>
        <div className="flex items-center gap-3">
          {workspaces.length > 0 && (
            <Select value={activeWorkspaceId} onValueChange={setSelectedWorkspaceId}>
              <SelectTrigger className="h-8 w-[200px] text-sm">
                <FolderOpen className="mr-2 h-3.5 w-3.5" />
                <SelectValue placeholder="Select workspace" />
              </SelectTrigger>
              <SelectContent>
                {workspaces.map((ws) => (
                  <SelectItem key={ws.id} value={ws.id}>
                    {ws.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-3 md:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Conversations</p>
                <p className="text-lg font-semibold">{conversations.length}</p>
              </div>
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Unread</p>
                <p className="text-lg font-semibold">{totalUnread}</p>
              </div>
              <AlertCircle className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Active Campaigns</p>
                <p className="text-lg font-semibold">
                  {campaigns.filter((c) => c.status === "running").length}
                </p>
              </div>
              <Megaphone className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-muted-foreground">Total Replies</p>
                <p className="text-lg font-semibold">
                  {campaigns.reduce((sum, c) => sum + c.replies_received, 0)}
                </p>
              </div>
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <div className="flex items-center justify-between">
          <TabsList>
            <TabsTrigger value="conversations" className="gap-2">
              <MessageSquare className="h-4 w-4" />
              Conversations
              {totalUnread > 0 && (
                <span className="ml-1 rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                  {totalUnread}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="campaigns" className="gap-2">
              <Megaphone className="h-4 w-4" />
              Campaigns
            </TabsTrigger>
          </TabsList>
          <div className="flex gap-2">
            {activeTab === "conversations" && (
              <Button size="sm" onClick={() => setIsNewMessageOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                New Message
              </Button>
            )}
            {activeTab === "campaigns" && (
              <Button size="sm" onClick={() => setIsNewCampaignOpen(true)}>
                <Plus className="mr-2 h-4 w-4" />
                New Campaign
              </Button>
            )}
          </div>
        </div>

        {/* Conversations Tab */}
        <TabsContent value="conversations" className="mt-4">
          {conversationsLoading ? (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </CardContent>
            </Card>
          ) : conversationsError ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="mb-4 h-12 w-12 text-destructive" />
                <p className="text-sm text-muted-foreground">Failed to load conversations</p>
              </CardContent>
            </Card>
          ) : conversations.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <MessageSquare className="mb-4 h-12 w-12 text-muted-foreground/50" />
                <h3 className="mb-2 text-lg font-semibold">No conversations yet</h3>
                <p className="mb-4 text-center text-sm text-muted-foreground">
                  Start a conversation by sending a message or receive inbound texts
                </p>
                <Button size="sm" onClick={() => setIsNewMessageOpen(true)}>
                  <Send className="mr-2 h-4 w-4" />
                  Send First Message
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-3">
              {conversations.map((conversation) => (
                <Link
                  key={conversation.id}
                  href={`/dashboard/sms/conversations/${conversation.id}`}
                >
                  <Card className="cursor-pointer transition-colors hover:bg-accent/50">
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                            {conversation.contact_name ? (
                              <User className="h-5 w-5 text-primary" />
                            ) : (
                              <Phone className="h-5 w-5 text-primary" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="font-medium">
                                {conversation.contact_name ?? conversation.to_number}
                              </p>
                              {conversation.unread_count > 0 && (
                                <span className="rounded-full bg-primary px-1.5 py-0.5 text-xs text-primary-foreground">
                                  {conversation.unread_count}
                                </span>
                              )}
                            </div>
                            <p className="truncate text-sm text-muted-foreground">
                              {conversation.last_message_direction === "outbound" && (
                                <CheckCheck className="mr-1 inline h-3 w-3" />
                              )}
                              {conversation.last_message_preview ?? "No messages yet"}
                            </p>
                          </div>
                        </div>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          {conversation.last_message_at && (
                            <span className="flex items-center gap-1">
                              <Clock className="h-3 w-3" />
                              {formatDistanceToNow(new Date(conversation.last_message_at), {
                                addSuffix: true,
                              })}
                            </span>
                          )}
                          <ArrowRight className="h-4 w-4" />
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Campaigns Tab */}
        <TabsContent value="campaigns" className="mt-4">
          {campaignsLoading ? (
            <Card>
              <CardContent className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </CardContent>
            </Card>
          ) : campaignsError ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <AlertCircle className="mb-4 h-12 w-12 text-destructive" />
                <p className="text-sm text-muted-foreground">Failed to load campaigns</p>
              </CardContent>
            </Card>
          ) : campaigns.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-12">
                <Megaphone className="mb-4 h-12 w-12 text-muted-foreground/50" />
                <h3 className="mb-2 text-lg font-semibold">No campaigns yet</h3>
                <p className="mb-4 text-center text-sm text-muted-foreground">
                  Create a campaign to send SMS to multiple contacts
                </p>
                <Button size="sm" onClick={() => setIsNewCampaignOpen(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Campaign
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-3">
              {campaigns.map((campaign) => (
                <Card key={campaign.id}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium">{campaign.name}</h3>
                          <span
                            className={`rounded-full px-2 py-0.5 text-xs ${getStatusBadge(campaign.status)}`}
                          >
                            {campaign.status}
                          </span>
                        </div>
                        {campaign.description && (
                          <p className="mt-1 text-sm text-muted-foreground">
                            {campaign.description}
                          </p>
                        )}
                        <div className="mt-3 flex flex-wrap gap-4 text-sm">
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <Users className="h-4 w-4" />
                            <span>{campaign.total_contacts} contacts</span>
                          </div>
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <Send className="h-4 w-4" />
                            <span>{campaign.messages_sent} sent</span>
                          </div>
                          <div className="flex items-center gap-1 text-muted-foreground">
                            <MessageSquare className="h-4 w-4" />
                            <span>{campaign.replies_received} replies</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        {campaign.status === "draft" || campaign.status === "paused" ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => startCampaignMutation.mutate(campaign.id)}
                            disabled={startCampaignMutation.isPending}
                          >
                            {startCampaignMutation.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              "Start"
                            )}
                          </Button>
                        ) : campaign.status === "running" ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => pauseCampaignMutation.mutate(campaign.id)}
                            disabled={pauseCampaignMutation.isPending}
                          >
                            {pauseCampaignMutation.isPending ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              "Pause"
                            )}
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* New Message Dialog */}
      <Dialog open={isNewMessageOpen} onOpenChange={setIsNewMessageOpen}>
        <DialogContent className="sm:max-w-[500px]">
          <DialogHeader>
            <DialogTitle>Send New Message</DialogTitle>
            <DialogDescription>Send an SMS to a phone number</DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="from_number">From Number</Label>
              <Select
                value={newMessageData.from_number}
                onValueChange={(value) => {
                  const selectedPhone = phoneNumbers.find((p) => p.phone_number === value);
                  setNewMessageData({
                    ...newMessageData,
                    from_number: value,
                    provider: selectedPhone?.provider ?? "telnyx",
                  });
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a phone number" />
                </SelectTrigger>
                <SelectContent>
                  {phoneNumbers.map((phone) => (
                    <SelectItem key={phone.id} value={phone.phone_number}>
                      {phone.phone_number}
                      {phone.friendly_name ? ` (${phone.friendly_name})` : null}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="to_number">To Number</Label>
              <Input
                id="to_number"
                placeholder="+1234567890"
                value={newMessageData.to_number}
                onChange={(e) =>
                  setNewMessageData({ ...newMessageData, to_number: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="body">Message</Label>
              <Textarea
                id="body"
                placeholder="Type your message..."
                value={newMessageData.body}
                onChange={(e) => setNewMessageData({ ...newMessageData, body: e.target.value })}
                rows={4}
              />
              <p className="text-xs text-muted-foreground">
                {newMessageData.body.length}/1600 characters
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsNewMessageOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleSendMessage} disabled={sendMessageMutation.isPending}>
              {sendMessageMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Send className="mr-2 h-4 w-4" />
              )}
              Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* New Campaign Dialog */}
      <Dialog open={isNewCampaignOpen} onOpenChange={setIsNewCampaignOpen}>
        <DialogContent className="sm:max-w-[600px]">
          <DialogHeader>
            <DialogTitle>Create SMS Campaign</DialogTitle>
            <DialogDescription>
              Send SMS messages to multiple contacts for lead qualification
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="max-h-[60vh]">
            <div className="grid gap-4 py-4 pr-4">
              <div className="space-y-2">
                <Label htmlFor="campaign_name">Campaign Name *</Label>
                <Input
                  id="campaign_name"
                  placeholder="e.g., January Lead Outreach"
                  value={newCampaignData.name}
                  onChange={(e) => setNewCampaignData({ ...newCampaignData, name: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="campaign_description">Description</Label>
                <Textarea
                  id="campaign_description"
                  placeholder="Optional campaign description..."
                  value={newCampaignData.description}
                  onChange={(e) =>
                    setNewCampaignData({ ...newCampaignData, description: e.target.value })
                  }
                  rows={2}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="from_phone_number">From Number *</Label>
                <Select
                  value={newCampaignData.from_phone_number}
                  onValueChange={(value) =>
                    setNewCampaignData({ ...newCampaignData, from_phone_number: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select a phone number" />
                  </SelectTrigger>
                  <SelectContent>
                    {phoneNumbers.map((phone) => (
                      <SelectItem key={phone.id} value={phone.phone_number}>
                        {phone.phone_number}
                        {phone.friendly_name ? ` (${phone.friendly_name})` : null}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="initial_message">Initial Message *</Label>
                <Textarea
                  id="initial_message"
                  placeholder="Hi {first_name}, this is [Your Company]..."
                  value={newCampaignData.initial_message}
                  onChange={(e) =>
                    setNewCampaignData({ ...newCampaignData, initial_message: e.target.value })
                  }
                  rows={4}
                />
                <p className="text-xs text-muted-foreground">
                  Use {"{first_name}"} and {"{company_name}"} for personalization
                </p>
              </div>
              <div className="space-y-2">
                <Label>Select Contacts ({selectedContactIds.length} selected)</Label>
                <ScrollArea className="h-[150px] rounded-md border p-2">
                  {contacts.length === 0 ? (
                    <p className="py-4 text-center text-sm text-muted-foreground">
                      No contacts found.{" "}
                      <Link href="/dashboard/crm" className="text-primary hover:underline">
                        Add contacts
                      </Link>{" "}
                      first.
                    </p>
                  ) : (
                    <div className="space-y-2">
                      {contacts.map((contact) => (
                        <label
                          key={contact.id}
                          className="flex cursor-pointer items-center gap-2 rounded p-2 hover:bg-accent"
                        >
                          <input
                            type="checkbox"
                            checked={selectedContactIds.includes(contact.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedContactIds([...selectedContactIds, contact.id]);
                              } else {
                                setSelectedContactIds(
                                  selectedContactIds.filter((id) => id !== contact.id)
                                );
                              }
                            }}
                            className="h-4 w-4 rounded border-gray-300"
                          />
                          <span className="text-sm">
                            {contact.first_name} {contact.last_name} - {contact.phone_number}
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </div>
            </div>
          </ScrollArea>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsNewCampaignOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateCampaign} disabled={createCampaignMutation.isPending}>
              {createCampaignMutation.isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-2 h-4 w-4" />
              )}
              Create Campaign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
