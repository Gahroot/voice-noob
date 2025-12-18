"use client";

import { use } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { getCall, type CallRecord, type EmotionEntry } from "@/lib/api/calls";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ArrowLeft,
  Phone,
  Clock,
  User,
  Bot,
  Play,
  Pause,
  Download,
  Loader2,
  AlertCircle,
  Heart,
  Activity,
  Smile,
  Frown,
  Meh,
} from "lucide-react";
import { useState, useRef, useMemo } from "react";
import { toast } from "sonner";

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatPhoneNumber(number: string): string {
  if (number.startsWith("+1") && number.length === 12) {
    return `(${number.slice(2, 5)}) ${number.slice(5, 8)}-${number.slice(8)}`;
  }
  return number;
}

// Emotion color mapping for visualization
const EMOTION_COLORS: Record<string, string> = {
  joy: "#10b981",
  excitement: "#f59e0b",
  interest: "#3b82f6",
  admiration: "#8b5cf6",
  love: "#ec4899",
  contentment: "#06b6d4",
  satisfaction: "#22c55e",
  relief: "#84cc16",
  amusement: "#fbbf24",
  pride: "#a855f7",
  calmness: "#14b8a6",
  concentration: "#6366f1",
  determination: "#f97316",
  anger: "#ef4444",
  fear: "#dc2626",
  anxiety: "#f87171",
  sadness: "#64748b",
  disappointment: "#94a3b8",
  disgust: "#854d0e",
  contempt: "#78716c",
  confusion: "#d97706",
  embarrassment: "#fb923c",
  guilt: "#475569",
  shame: "#334155",
  boredom: "#9ca3af",
  tiredness: "#6b7280",
};

// Get emoji for emotion
function getEmotionEmoji(emotion: string): string {
  const positive = [
    "joy",
    "excitement",
    "interest",
    "love",
    "contentment",
    "satisfaction",
    "amusement",
    "pride",
  ];
  const negative = ["anger", "fear", "anxiety", "sadness", "disappointment", "disgust"];

  if (positive.includes(emotion)) return "positive";
  if (negative.includes(emotion)) return "negative";
  return "neutral";
}

// Emotion badge component
function EmotionBadge({ emotion, score }: { emotion: string; score: number }) {
  const color = EMOTION_COLORS[emotion] ?? "#6b7280";
  const sentiment = getEmotionEmoji(emotion);

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium"
      style={{
        backgroundColor: `${color}20`,
        color: color,
        border: `1px solid ${color}40`,
      }}
    >
      {sentiment === "positive" && <Smile className="h-3 w-3" />}
      {sentiment === "negative" && <Frown className="h-3 w-3" />}
      {sentiment === "neutral" && <Meh className="h-3 w-3" />}
      <span className="capitalize">{emotion.replace(/_/g, " ")}</span>
      <span className="opacity-70">{(score * 100).toFixed(0)}%</span>
    </motion.div>
  );
}

// Emotion timeline entry
function EmotionTimelineEntry({ entry, index }: { entry: EmotionEntry; index: number }) {
  const topEmotions = useMemo(() => {
    return Object.entries(entry.emotions)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3);
  }, [entry.emotions]);

  const sentiment = useMemo(() => {
    const firstEmotion = topEmotions[0];
    if (!firstEmotion) return "neutral";
    return getEmotionEmoji(firstEmotion[0]);
  }, [topEmotions]);

  return (
    <motion.div
      initial={{ x: -20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ delay: index * 0.05 }}
      className={`flex gap-4 rounded-lg p-3 ${
        entry.role === "user" ? "bg-blue-500/5" : "bg-green-500/5"
      }`}
    >
      <div className="flex-shrink-0">
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full ${
            entry.role === "user" ? "bg-blue-500/20" : "bg-green-500/20"
          }`}
        >
          {entry.role === "user" ? (
            <User className="h-4 w-4 text-blue-500" />
          ) : (
            <Bot className="h-4 w-4 text-green-500" />
          )}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-2 flex items-center gap-2">
          <span className="text-sm font-medium capitalize">{entry.role}</span>
          <span className="text-xs text-muted-foreground">
            {new Date(entry.timestamp).toLocaleTimeString()}
          </span>
          {sentiment === "positive" && (
            <Badge variant="secondary" className="bg-green-500/10 text-xs text-green-600">
              <Smile className="mr-1 h-3 w-3" /> Positive
            </Badge>
          )}
          {sentiment === "negative" && (
            <Badge variant="secondary" className="bg-red-500/10 text-xs text-red-600">
              <Frown className="mr-1 h-3 w-3" /> Negative
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {topEmotions.map(([emotion, score]) => (
            <EmotionBadge key={emotion} emotion={emotion} score={score} />
          ))}
        </div>
      </div>
    </motion.div>
  );
}

// Emotion summary visualization
function EmotionSummaryChart({ call }: { call: CallRecord }) {
  const topEmotions = call.emotion_data?.summary?.top_user_emotions ?? [];

  if (topEmotions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <Heart className="mb-4 h-12 w-12 opacity-20" />
        <p>No emotion data available</p>
      </div>
    );
  }

  const maxScore = Math.max(...topEmotions.map((e) => e.score));

  return (
    <div className="space-y-4">
      <div className="mb-4 flex items-center gap-2 text-sm text-muted-foreground">
        <Activity className="h-4 w-4" />
        <span>Top emotions detected from caller</span>
      </div>
      {topEmotions.map((item, index) => {
        const color = EMOTION_COLORS[item.emotion] ?? "#6b7280";
        const percentage = (item.score / maxScore) * 100;

        return (
          <motion.div
            key={item.emotion}
            initial={{ width: 0 }}
            animate={{ width: "100%" }}
            transition={{ delay: index * 0.1, duration: 0.5 }}
            className="space-y-1"
          >
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium capitalize" style={{ color }}>
                {item.emotion.replace(/_/g, " ")}
              </span>
              <span className="text-muted-foreground">{(item.score * 100).toFixed(1)}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-muted">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${percentage}%` }}
                transition={{ delay: index * 0.1 + 0.2, duration: 0.5 }}
                className="h-full rounded-full"
                style={{ backgroundColor: color }}
              />
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

export default function CallDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);

  const {
    data: call,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["call", id],
    queryFn: () => getCall(id),
  });

  const handlePlayRecording = () => {
    if (!call?.recording_url) {
      toast.error("No recording available for this call");
      return;
    }

    if (isPlaying && audioRef.current) {
      audioRef.current.pause();
      setIsPlaying(false);
      return;
    }

    if (audioRef.current) {
      audioRef.current.pause();
    }

    const audio = new Audio(call.recording_url);
    audioRef.current = audio;
    setIsPlaying(true);

    audio.play().catch((err: Error) => {
      toast.error(`Failed to play recording: ${err.message}`);
      setIsPlaying(false);
    });

    audio.onended = () => {
      setIsPlaying(false);
    };
  };

  const handleDownloadTranscript = () => {
    if (!call?.transcript) {
      toast.error("No transcript available for this call");
      return;
    }

    const blob = new Blob([call.transcript], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `transcript-${call.id}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success("Transcript download started");
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <Loader2 className="mb-4 h-16 w-16 animate-spin text-muted-foreground/50" />
        <p className="text-muted-foreground">Loading call details...</p>
      </div>
    );
  }

  if (error instanceof Error) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <AlertCircle className="mb-4 h-16 w-16 text-destructive" />
        <h3 className="mb-2 text-lg font-semibold">Failed to load call</h3>
        <p className="max-w-sm text-center text-sm text-muted-foreground">{error.message}</p>
        <Button variant="outline" className="mt-4" asChild>
          <Link href="/dashboard/calls">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Calls
          </Link>
        </Button>
      </div>
    );
  }

  if (!call) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <AlertCircle className="mb-4 h-16 w-16 text-muted-foreground" />
        <h3 className="mb-2 text-lg font-semibold">Call not found</h3>
        <Button variant="outline" className="mt-4" asChild>
          <Link href="/dashboard/calls">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Calls
          </Link>
        </Button>
      </div>
    );
  }

  const hasEmotionData = call.emotion_data?.summary?.has_emotion_data ?? false;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/dashboard/calls">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div>
            <h1 className="text-xl font-semibold">Call Details</h1>
            <p className="text-sm text-muted-foreground">
              {new Date(call.started_at).toLocaleString()}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {call.recording_url && (
            <Button variant="outline" size="sm" onClick={handlePlayRecording}>
              {isPlaying ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
              {isPlaying ? "Pause" : "Play Recording"}
            </Button>
          )}
          {call.transcript && (
            <Button variant="outline" size="sm" onClick={handleDownloadTranscript}>
              <Download className="mr-2 h-4 w-4" />
              Download Transcript
            </Button>
          )}
        </div>
      </div>

      {/* Call Info Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Phone className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Direction</p>
              <p className="font-medium capitalize">{call.direction}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Clock className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Duration</p>
              <p className="font-medium">{formatDuration(call.duration_seconds)}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <User className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">
                {call.direction === "inbound" ? "Caller" : "Recipient"}
              </p>
              <p className="font-mono text-sm font-medium">
                {call.direction === "inbound"
                  ? formatPhoneNumber(call.from_number)
                  : formatPhoneNumber(call.to_number)}
              </p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Agent</p>
              <p className="font-medium">{call.agent_name ?? "Unknown"}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Status and Provider */}
      <div className="flex items-center gap-2">
        <Badge variant={call.status === "completed" ? "default" : "destructive"}>
          {call.status.replace("_", " ")}
        </Badge>
        <Badge variant="outline">{call.provider}</Badge>
        {hasEmotionData && (
          <Badge variant="secondary" className="bg-pink-500/10 text-pink-600">
            <Heart className="mr-1 h-3 w-3" />
            Emotion Data
          </Badge>
        )}
      </div>

      {/* Tabs for Transcript and Emotions */}
      <Tabs defaultValue={hasEmotionData ? "emotions" : "transcript"} className="w-full">
        <TabsList>
          <TabsTrigger value="transcript">Transcript</TabsTrigger>
          {hasEmotionData && (
            <TabsTrigger value="emotions">
              <Heart className="mr-2 h-4 w-4" />
              Emotions
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="transcript" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Conversation Transcript</CardTitle>
              <CardDescription>Full transcript of the conversation</CardDescription>
            </CardHeader>
            <CardContent>
              {call.transcript ? (
                <div className="max-h-[500px] overflow-y-auto whitespace-pre-wrap rounded-lg bg-muted/50 p-4 font-mono text-sm">
                  {call.transcript}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                  <p>No transcript available for this call</p>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {hasEmotionData && (
          <TabsContent value="emotions" className="mt-4">
            <div className="grid gap-6 lg:grid-cols-2">
              {/* Emotion Summary */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5" />
                    Emotion Summary
                  </CardTitle>
                  <CardDescription>Overall emotional analysis of the caller</CardDescription>
                </CardHeader>
                <CardContent>
                  <EmotionSummaryChart call={call} />
                  <Separator className="my-4" />
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Total Measurements</p>
                      <p className="font-medium">
                        {call.emotion_data?.summary?.total_measurements ?? 0}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">User Measurements</p>
                      <p className="font-medium">
                        {call.emotion_data?.summary?.user_measurements ?? 0}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Emotion Timeline */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Heart className="h-5 w-5" />
                    Emotion Timeline
                  </CardTitle>
                  <CardDescription>Emotions detected throughout the conversation</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="max-h-[400px] space-y-3 overflow-y-auto">
                    {(call.emotion_data?.entries ?? []).length > 0 ? (
                      call.emotion_data?.entries.map((entry, index) => (
                        <EmotionTimelineEntry
                          key={`${entry.timestamp}-${index}`}
                          entry={entry}
                          index={index}
                        />
                      ))
                    ) : (
                      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                        <p>No timeline data available</p>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
