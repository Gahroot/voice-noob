"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  MessageSquare,
  Send,
  Plus,
  Loader2,
  AlertCircle,
  Clock,
  CheckCheck,
  Check,
  XCircle,
  User,
  Phone,
  ArrowRight,
  Megaphone,
  Users,
  FolderOpen,
  Bot,
  Search,
  MoreVertical,
  Pause,
  Play,
  UserMinus,
  ChevronLeft,
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
  getConversationMessages,
  markConversationRead,
  listTextAgents,
  assignAgentToConversation,
  updateConversationAISettings,
  type SMSConversation,
  type SMSCampaign,
  type SMSMessage,
  type TextAgent,
  type CreateCampaignRequest,
} from "@/lib/api/sms";
import { listPhoneNumbers, type PhoneNumber } from "@/lib/api/telephony";
import { fetchSettings } from "@/lib/api/settings";
import Link from "next/link";
import { formatDistanceToNow, format, isToday, isYesterday } from "date-fns";
import { cn } from "@/lib/utils";

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
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [isNewMessageOpen, setIsNewMessageOpen] = useState(false);
  const [isNewCampaignOpen, setIsNewCampaignOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [newMessage, setNewMessage] = useState("");
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
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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
    refetchInterval: 10000, // Refresh conversation list every 10 seconds
  });

  // Filter conversations based on search
  const filteredConversations = conversations.filter((c) => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return (
      c.contact_name?.toLowerCase().includes(query) ??
      c.to_number.includes(query) ??
      c.last_message_preview?.toLowerCase().includes(query)
    );
  });

  // Get selected conversation
  const selectedConversation = conversations.find((c) => c.id === selectedConversationId);

  // Fetch messages for selected conversation
  const { data: messages = [], isLoading: messagesLoading } = useQuery<SMSMessage[]>({
    queryKey: ["sms-messages", selectedConversationId],
    queryFn: () => {
      if (!selectedConversationId) throw new Error("No conversation selected");
      return getConversationMessages(selectedConversationId);
    },
    enabled: !!selectedConversationId,
    refetchInterval: 3000, // Poll for new messages every 3 seconds
  });

  // Fetch text agents for AI controls
  const { data: textAgents = [] } = useQuery<TextAgent[]>({
    queryKey: ["text-agents", activeWorkspaceId],
    queryFn: () => listTextAgents(activeWorkspaceId),
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
      const telnyxNumbers = await listPhoneNumbers("telnyx", activeWorkspaceId);
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

  // Mark conversation as read when selected
  useEffect(() => {
    if (
      selectedConversationId &&
      selectedConversation?.unread_count &&
      selectedConversation.unread_count > 0 &&
      activeWorkspaceId
    ) {
      void markConversationRead(selectedConversationId, activeWorkspaceId).then(() => {
        void queryClient.invalidateQueries({ queryKey: ["sms-conversations", activeWorkspaceId] });
      });
    }
  }, [selectedConversationId, selectedConversation?.unread_count, activeWorkspaceId, queryClient]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input when conversation selected
  useEffect(() => {
    if (selectedConversationId) {
      inputRef.current?.focus();
    }
  }, [selectedConversationId]);

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: async (body: string) => {
      if (!selectedConversation || !selectedConversationId) {
        throw new Error("No conversation selected");
      }
      return sendMessage(
        {
          to_number: selectedConversation.to_number,
          from_number: selectedConversation.from_number,
          body,
          conversation_id: selectedConversationId,
        },
        activeWorkspaceId
      );
    },
    onSuccess: () => {
      setNewMessage("");
      void queryClient.invalidateQueries({ queryKey: ["sms-messages", selectedConversationId] });
      void queryClient.invalidateQueries({ queryKey: ["sms-conversations", activeWorkspaceId] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to send message");
    },
  });

  // New conversation send mutation
  const sendNewMessageMutation = useMutation({
    mutationFn: async (data: typeof newMessageData) => {
      return sendMessage(data, activeWorkspaceId);
    },
    onSuccess: (response) => {
      toast.success("Message sent!");
      setIsNewMessageOpen(false);
      setNewMessageData({ to_number: "", from_number: "", body: "", provider: "telnyx" });
      void queryClient.invalidateQueries({ queryKey: ["sms-conversations"] });
      // Auto-select the new conversation if we can find it
      if (response) {
        void queryClient
          .invalidateQueries({ queryKey: ["sms-conversations", activeWorkspaceId] })
          .then(() => {
            // The conversation should appear in the list now
          });
      }
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to send message");
    },
  });

  // AI agent mutations
  const assignAgentMutation = useMutation({
    mutationFn: async ({
      conversationId,
      agentId,
    }: {
      conversationId: string;
      agentId: string | null;
    }) => {
      return assignAgentToConversation(conversationId, { agent_id: agentId });
    },
    onSuccess: () => {
      toast.success("Agent assignment updated");
      void queryClient.invalidateQueries({ queryKey: ["sms-conversations", activeWorkspaceId] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to update agent");
    },
  });

  const toggleAIPausedMutation = useMutation({
    mutationFn: async ({ conversationId, paused }: { conversationId: string; paused: boolean }) => {
      return updateConversationAISettings(conversationId, { ai_paused: paused });
    },
    onSuccess: (_, variables) => {
      toast.success(variables.paused ? "AI paused" : "AI resumed");
      void queryClient.invalidateQueries({ queryKey: ["sms-conversations", activeWorkspaceId] });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to update AI settings");
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

  const handleSend = useCallback(() => {
    if (!newMessage.trim()) return;
    sendMessageMutation.mutate(newMessage.trim());
  }, [newMessage, sendMessageMutation]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSendNewMessage = () => {
    if (!newMessageData.to_number || !newMessageData.from_number || !newMessageData.body) {
      toast.error("Please fill in all fields");
      return;
    }
    sendNewMessageMutation.mutate(newMessageData);
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

  const formatMessageTime = (dateStr: string) => {
    const date = new Date(dateStr);
    if (isToday(date)) {
      return format(date, "h:mm a");
    }
    if (isYesterday(date)) {
      return `Yesterday ${format(date, "h:mm a")}`;
    }
    return format(date, "MMM d, h:mm a");
  };

  const formatConversationTime = (dateStr: string | null) => {
    if (!dateStr) return "";
    return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "delivered":
        return <CheckCheck className="h-3 w-3 text-blue-500" />;
      case "sent":
        return <Check className="h-3 w-3 text-muted-foreground" />;
      case "failed":
      case "undelivered":
        return <XCircle className="h-3 w-3 text-destructive" />;
      default:
        return <Clock className="h-3 w-3 text-muted-foreground" />;
    }
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

  // Sort messages oldest to newest for display
  const sortedMessages = [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

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
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-4">
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

      {/* Tabs */}
      <Tabs
        value={activeTab}
        onValueChange={(v) => setActiveTab(v as typeof activeTab)}
        className="flex flex-1 flex-col overflow-hidden"
      >
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

        {/* Conversations Tab - Split View */}
        <TabsContent value="conversations" className="mt-4 flex-1 overflow-hidden">
          <div className="flex h-full overflow-hidden rounded-lg border bg-background">
            {/* Conversation List */}
            <div
              className={cn(
                "flex w-full flex-col border-r md:w-80 lg:w-96",
                selectedConversationId && "hidden md:flex"
              )}
            >
              {/* Search */}
              <div className="border-b p-3">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    placeholder="Search conversations..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>
              </div>

              {/* List */}
              <ScrollArea className="flex-1">
                {conversationsLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : conversationsError ? (
                  <div className="flex flex-col items-center justify-center py-12">
                    <AlertCircle className="mb-2 h-8 w-8 text-destructive" />
                    <p className="text-sm text-muted-foreground">Failed to load</p>
                  </div>
                ) : filteredConversations.length === 0 ? (
                  <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
                    <MessageSquare className="mb-4 h-10 w-10 text-muted-foreground/50" />
                    <p className="text-sm font-medium">No conversations</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Start a conversation by sending a message
                    </p>
                  </div>
                ) : (
                  <div className="divide-y">
                    {filteredConversations.map((conversation) => (
                      <button
                        key={conversation.id}
                        onClick={() => setSelectedConversationId(conversation.id)}
                        className={cn(
                          "w-full p-3 text-left transition-colors hover:bg-accent/50",
                          selectedConversationId === conversation.id && "bg-accent"
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
                            {conversation.contact_name ? (
                              <User className="h-5 w-5 text-primary" />
                            ) : (
                              <Phone className="h-5 w-5 text-primary" />
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <span className="truncate font-medium">
                                {conversation.contact_name ?? conversation.to_number}
                              </span>
                              <span className="flex-shrink-0 text-xs text-muted-foreground">
                                {formatConversationTime(conversation.last_message_at)}
                              </span>
                            </div>
                            <div className="mt-0.5 flex items-center gap-2">
                              <p className="truncate text-sm text-muted-foreground">
                                {conversation.last_message_direction === "outbound" && (
                                  <CheckCheck className="mr-1 inline h-3 w-3" />
                                )}
                                {conversation.last_message_preview ?? "No messages yet"}
                              </p>
                            </div>
                            <div className="mt-1 flex items-center gap-2">
                              {conversation.unread_count > 0 && (
                                <Badge variant="default" className="h-5 px-1.5 text-xs">
                                  {conversation.unread_count}
                                </Badge>
                              )}
                              {conversation.assigned_agent_id && (
                                <Badge variant="secondary" className="h-5 gap-1 px-1.5 text-xs">
                                  <Bot className="h-3 w-3" />
                                  {conversation.ai_paused ? "Paused" : "AI"}
                                </Badge>
                              )}
                            </div>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </ScrollArea>
            </div>

            {/* Message Thread */}
            <div
              className={cn("flex flex-1 flex-col", !selectedConversationId && "hidden md:flex")}
            >
              {selectedConversation ? (
                <>
                  {/* Thread Header */}
                  <div className="flex items-center gap-3 border-b p-3">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="md:hidden"
                      onClick={() => setSelectedConversationId(null)}
                    >
                      <ChevronLeft className="h-5 w-5" />
                    </Button>
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                      {selectedConversation.contact_name ? (
                        <User className="h-5 w-5 text-primary" />
                      ) : (
                        <Phone className="h-5 w-5 text-primary" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h2 className="truncate font-semibold">
                        {selectedConversation.contact_name ?? selectedConversation.to_number}
                      </h2>
                      <p className="truncate text-xs text-muted-foreground">
                        {selectedConversation.from_number} → {selectedConversation.to_number}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {selectedConversation.contact_id && (
                        <Link href={`/dashboard/crm?contact=${selectedConversation.contact_id}`}>
                          <Button variant="ghost" size="sm">
                            View in CRM
                            <ArrowRight className="ml-1 h-3 w-3" />
                          </Button>
                        </Link>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-56">
                          <DropdownMenuLabel>AI Agent</DropdownMenuLabel>
                          <DropdownMenuSub>
                            <DropdownMenuSubTrigger>
                              <Bot className="mr-2 h-4 w-4" />
                              {selectedConversation.assigned_agent_id
                                ? (selectedConversation.assigned_agent_name ?? "Assigned")
                                : "Assign Agent"}
                            </DropdownMenuSubTrigger>
                            <DropdownMenuSubContent className="w-48">
                              {textAgents.length === 0 ? (
                                <DropdownMenuItem disabled>
                                  <span className="text-muted-foreground">
                                    No text agents available
                                  </span>
                                </DropdownMenuItem>
                              ) : (
                                textAgents.map((agent) => (
                                  <DropdownMenuItem
                                    key={agent.id}
                                    onClick={() =>
                                      assignAgentMutation.mutate({
                                        conversationId: selectedConversation.id,
                                        agentId: agent.id,
                                      })
                                    }
                                  >
                                    <Bot className="mr-2 h-4 w-4" />
                                    <span className="flex-1">{agent.name}</span>
                                    {selectedConversation.assigned_agent_id === agent.id && (
                                      <Check className="ml-2 h-4 w-4" />
                                    )}
                                  </DropdownMenuItem>
                                ))
                              )}
                              {selectedConversation.assigned_agent_id && (
                                <>
                                  <DropdownMenuSeparator />
                                  <DropdownMenuItem
                                    onClick={() =>
                                      assignAgentMutation.mutate({
                                        conversationId: selectedConversation.id,
                                        agentId: null,
                                      })
                                    }
                                  >
                                    <UserMinus className="mr-2 h-4 w-4" />
                                    Remove Agent
                                  </DropdownMenuItem>
                                </>
                              )}
                            </DropdownMenuSubContent>
                          </DropdownMenuSub>
                          {selectedConversation.assigned_agent_id && (
                            <>
                              <DropdownMenuSeparator />
                              <DropdownMenuItem
                                onClick={() =>
                                  toggleAIPausedMutation.mutate({
                                    conversationId: selectedConversation.id,
                                    paused: !selectedConversation.ai_paused,
                                  })
                                }
                              >
                                {selectedConversation.ai_paused ? (
                                  <>
                                    <Play className="mr-2 h-4 w-4" />
                                    Resume AI
                                  </>
                                ) : (
                                  <>
                                    <Pause className="mr-2 h-4 w-4" />
                                    Pause AI
                                  </>
                                )}
                              </DropdownMenuItem>
                            </>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>

                  {/* Messages */}
                  <ScrollArea className="flex-1 p-4">
                    <div className="space-y-3">
                      {messagesLoading ? (
                        <div className="flex items-center justify-center py-12">
                          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                        </div>
                      ) : sortedMessages.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-center">
                          <Send className="mb-4 h-10 w-10 text-muted-foreground/50" />
                          <p className="text-sm text-muted-foreground">
                            No messages yet. Start the conversation!
                          </p>
                        </div>
                      ) : (
                        sortedMessages.map((message, index) => {
                          const isOutbound = message.direction === "outbound";
                          const prevMessage = sortedMessages[index - 1];
                          const showTimestamp =
                            index === 0 ||
                            (prevMessage &&
                              new Date(message.created_at).getTime() -
                                new Date(prevMessage.created_at).getTime() >
                                300000);

                          return (
                            <div key={message.id}>
                              {showTimestamp && (
                                <div className="my-4 flex justify-center">
                                  <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
                                    {formatMessageTime(message.created_at)}
                                  </span>
                                </div>
                              )}
                              <div
                                className={cn(
                                  "flex animate-[fadeIn_0.2s_ease-out_forwards] opacity-0",
                                  isOutbound ? "justify-end" : "justify-start"
                                )}
                                style={{ animationDelay: `${Math.min(index * 30, 300)}ms` }}
                              >
                                <div className="max-w-[75%] space-y-1">
                                  {message.agent_id && (
                                    <div
                                      className={cn(
                                        "flex items-center gap-1 text-[10px] text-muted-foreground",
                                        isOutbound && "justify-end"
                                      )}
                                    >
                                      <Bot className="h-3 w-3" />
                                      AI Agent
                                    </div>
                                  )}
                                  <div
                                    className={cn(
                                      "rounded-2xl px-4 py-2.5",
                                      isOutbound
                                        ? "rounded-br-md bg-primary text-primary-foreground"
                                        : "rounded-bl-md bg-muted"
                                    )}
                                  >
                                    <p className="whitespace-pre-wrap break-words text-sm">
                                      {message.body}
                                    </p>
                                  </div>
                                  <div
                                    className={cn(
                                      "flex items-center gap-1.5 px-1 text-[10px]",
                                      isOutbound ? "justify-end" : ""
                                    )}
                                  >
                                    <span className="text-muted-foreground">
                                      {format(new Date(message.created_at), "h:mm a")}
                                    </span>
                                    {isOutbound && getStatusIcon(message.status)}
                                  </div>
                                  {message.error_message && (
                                    <p className="px-1 text-[10px] text-destructive">
                                      {message.error_message}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </div>
                          );
                        })
                      )}
                      <div ref={messagesEndRef} />
                    </div>
                  </ScrollArea>

                  {/* Input */}
                  <div className="border-t p-3">
                    <div className="flex gap-2">
                      <Input
                        ref={inputRef}
                        placeholder="Type a message..."
                        value={newMessage}
                        onChange={(e) => setNewMessage(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={sendMessageMutation.isPending}
                        className="flex-1"
                      />
                      <Button
                        onClick={handleSend}
                        disabled={!newMessage.trim() || sendMessageMutation.isPending}
                      >
                        {sendMessageMutation.isPending ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Send className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
                  <div className="mb-4 rounded-full bg-muted p-4">
                    <MessageSquare className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <h3 className="mb-1 font-semibold">Select a conversation</h3>
                  <p className="mb-4 text-sm text-muted-foreground">
                    Choose a conversation from the list or start a new one
                  </p>
                  <Button variant="outline" onClick={() => setIsNewMessageOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    New Message
                  </Button>
                </div>
              )}
            </div>
          </div>
        </TabsContent>

        {/* Campaigns Tab */}
        <TabsContent value="campaigns" className="mt-4 flex-1 overflow-auto">
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
            <Button onClick={handleSendNewMessage} disabled={sendNewMessageMutation.isPending}>
              {sendNewMessageMutation.isPending ? (
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
