"use client";

import { useState, useEffect, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
// Card components available if needed for future enhancements
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  ArrowLeft,
  Send,
  Loader2,
  AlertCircle,
  User,
  Phone,
  Clock,
  CheckCheck,
  Check,
  XCircle,
  Bot,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import {
  getConversation,
  getConversationMessages,
  markConversationRead,
  sendMessage,
  type SMSConversation,
  type SMSMessage,
} from "@/lib/api/sms";
import { format, isToday, isYesterday } from "date-fns";
import Link from "next/link";

export default function ConversationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const conversationId = params.id as string;
  const workspaceId = searchParams.get("workspace_id") ?? "";
  const [newMessage, setNewMessage] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Fetch conversation
  const {
    data: conversation,
    isLoading: conversationLoading,
    error: conversationError,
  } = useQuery<SMSConversation>({
    queryKey: ["sms-conversation", conversationId, workspaceId],
    queryFn: () => getConversation(conversationId, workspaceId),
    enabled: !!conversationId && !!workspaceId,
  });

  // Fetch messages
  const {
    data: messages = [],
    isLoading: messagesLoading,
    error: messagesError,
  } = useQuery<SMSMessage[]>({
    queryKey: ["sms-messages", conversationId, workspaceId],
    queryFn: () => getConversationMessages(conversationId, workspaceId),
    enabled: !!conversationId && !!workspaceId,
    refetchInterval: 5000, // Poll for new messages every 5 seconds
  });

  // Mark as read when viewing
  useEffect(() => {
    if (conversation && conversation.unread_count > 0 && workspaceId) {
      void markConversationRead(conversationId, workspaceId).then(() => {
        void queryClient.invalidateQueries({ queryKey: ["sms-conversations"] });
      });
    }
  }, [conversation, conversationId, workspaceId, queryClient]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Send message mutation
  const sendMessageMutation = useMutation({
    mutationFn: async (body: string) => {
      if (!conversation || !workspaceId) throw new Error("No conversation or workspace");
      return sendMessage(
        {
          to_number: conversation.to_number,
          from_number: conversation.from_number,
          body,
          conversation_id: conversationId,
        },
        workspaceId
      );
    },
    onSuccess: () => {
      setNewMessage("");
      void queryClient.invalidateQueries({
        queryKey: ["sms-messages", conversationId, workspaceId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["sms-conversation", conversationId, workspaceId],
      });
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to send message");
    },
  });

  const handleSend = () => {
    if (!newMessage.trim()) return;
    sendMessageMutation.mutate(newMessage.trim());
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
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

  // Check for missing workspace_id
  if (!workspaceId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-muted-foreground">Missing workspace context</p>
        <Button variant="outline" onClick={() => router.push("/dashboard/sms")}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Go to SMS Dashboard
        </Button>
      </div>
    );
  }

  if (conversationLoading || messagesLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (conversationError || messagesError || !conversation) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load conversation</p>
        <Button variant="outline" onClick={() => router.back()}>
          <ArrowLeft className="mr-2 h-4 w-4" />
          Go Back
        </Button>
      </div>
    );
  }

  // Sort messages oldest to newest for display
  const sortedMessages = [...messages].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-4 border-b pb-4">
        <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard/sms")}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            {conversation.contact_name ? (
              <User className="h-5 w-5 text-primary" />
            ) : (
              <Phone className="h-5 w-5 text-primary" />
            )}
          </div>
          <div>
            <h1 className="font-semibold">{conversation.contact_name ?? conversation.to_number}</h1>
            <p className="text-sm text-muted-foreground">
              {conversation.contact_name ? conversation.to_number : null}
            </p>
          </div>
        </div>
        {conversation.contact_id && (
          <Link
            href={`/dashboard/crm?contact=${conversation.contact_id}`}
            className="ml-auto text-sm text-primary hover:underline"
          >
            View in CRM
          </Link>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4">
        <div className="space-y-4">
          {sortedMessages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Send className="mb-4 h-12 w-12 text-muted-foreground/50" />
              <p className="text-muted-foreground">No messages yet. Start the conversation!</p>
            </div>
          ) : (
            sortedMessages.map((message) => (
              <div
                key={message.id}
                className={cn(
                  "flex",
                  message.direction === "outbound" ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[70%] rounded-lg px-4 py-2",
                    message.direction === "outbound"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted"
                  )}
                >
                  {message.agent_id && (
                    <div className="mb-1 flex items-center gap-1 text-xs opacity-70">
                      <Bot className="h-3 w-3" />
                      AI Agent
                    </div>
                  )}
                  <p className="whitespace-pre-wrap break-words text-sm">{message.body}</p>
                  <div
                    className={cn(
                      "mt-1 flex items-center gap-1 text-xs",
                      message.direction === "outbound"
                        ? "justify-end text-primary-foreground/70"
                        : "text-muted-foreground"
                    )}
                  >
                    <span>{formatMessageTime(message.created_at)}</span>
                    {message.direction === "outbound" && getStatusIcon(message.status)}
                  </div>
                  {message.error_message && (
                    <p className="mt-1 text-xs text-destructive">{message.error_message}</p>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t p-4">
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
        <p className="mt-2 text-xs text-muted-foreground">
          Sending from {conversation.from_number}
        </p>
      </div>
    </div>
  );
}
