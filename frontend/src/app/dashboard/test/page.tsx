"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Phone, PhoneOff, Mic, MicOff } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";

export default function TestAgentPage() {
  const [isConnected, setIsConnected] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [transcript, setTranscript] = useState<
    Array<{ id: string; speaker: string; text: string; timestamp: Date }>
  >([]);

  const handleConnect = () => {
    setIsConnected(!isConnected);
    if (!isConnected) {
      // Simulate connection
      setTranscript([
        {
          id: crypto.randomUUID(),
          speaker: "Agent",
          text: "Hello! How can I help you today?",
          timestamp: new Date(),
        },
      ]);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Test Voice Agent</h1>
        <p className="text-muted-foreground">
          Test your voice agents in real-time before deployment
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Live Testing</CardTitle>
            <CardDescription>Connect to test your agent&apos;s conversation flow</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Select Agent</Label>
                <Select>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose an agent to test" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">No agents available</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Test Phone Number</Label>
                <Input type="tel" placeholder="+1 (555) 000-0000" disabled={isConnected} />
              </div>
            </div>

            <div className="flex gap-2 pt-4">
              <Button
                onClick={handleConnect}
                variant={isConnected ? "destructive" : "default"}
                className="flex-1"
              >
                {isConnected ? (
                  <>
                    <PhoneOff className="mr-2 h-4 w-4" />
                    End Call
                  </>
                ) : (
                  <>
                    <Phone className="mr-2 h-4 w-4" />
                    Start Test Call
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                onClick={() => setIsMuted(!isMuted)}
                disabled={!isConnected}
              >
                {isMuted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </Button>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Call Status</Label>
                <Badge variant={isConnected ? "default" : "secondary"}>
                  {isConnected ? "Connected" : "Disconnected"}
                </Badge>
              </div>

              <Card className="bg-muted/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">Live Transcript</CardTitle>
                </CardHeader>
                <CardContent>
                  <ScrollArea className="h-[300px] w-full rounded-md">
                    {transcript.length === 0 ? (
                      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                        Start a test call to see the live transcript
                      </div>
                    ) : (
                      <div className="space-y-3">
                        {transcript.map((item) => (
                          <div key={item.id} className="space-y-1">
                            <div className="flex items-center gap-2">
                              <Badge variant="outline" className="text-xs">
                                {item.speaker}
                              </Badge>
                              <span className="text-xs text-muted-foreground">
                                {item.timestamp.toLocaleTimeString()}
                              </span>
                            </div>
                            <p className="text-sm">{item.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </ScrollArea>
                </CardContent>
              </Card>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Test Metrics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Latency</span>
                <span className="font-mono">{isConnected ? "~150ms" : "—"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Duration</span>
                <span className="font-mono">{isConnected ? "00:00" : "—"}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Turns</span>
                <span className="font-mono">{transcript.length}</span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Debug Info</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 font-mono text-xs">
              <div className="grid grid-cols-2 gap-1">
                <span className="text-muted-foreground">STT:</span>
                <span>{isConnected ? "Active" : "Idle"}</span>
              </div>
              <div className="grid grid-cols-2 gap-1">
                <span className="text-muted-foreground">TTS:</span>
                <span>{isConnected ? "Active" : "Idle"}</span>
              </div>
              <div className="grid grid-cols-2 gap-1">
                <span className="text-muted-foreground">LLM:</span>
                <span>{isConnected ? "Active" : "Idle"}</span>
              </div>
              <div className="grid grid-cols-2 gap-1">
                <span className="text-muted-foreground">WebSocket:</span>
                <span>{isConnected ? "Connected" : "Disconnected"}</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-amber-500/50 bg-amber-500/5">
            <CardHeader>
              <CardTitle className="text-sm">Test Mode</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-xs text-muted-foreground">
                This is a testing interface. Calls made here will not be billed and will not appear
                in call history.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
