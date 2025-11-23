"use client";

import { useState, useMemo } from "react";
import { useDebounce } from "use-debounce";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { History, Download, Play } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Call = {
  id: string;
  timestamp: string;
  agentName: string;
  direction: string;
  phoneNumber: string;
  duration: string;
  status: string;
  recordingUrl?: string;
  transcriptUrl?: string;
};

export default function CallHistoryPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedSearchQuery] = useDebounce(searchQuery, 300);
  const [statusFilter, setStatusFilter] = useState("all");

  // Mock data - will be replaced with API call
  // Memoize to prevent the dependency warning
  const calls: Call[] = useMemo(() => [], []);

  // Memoize filtered calls to prevent unnecessary recalculations
  const filteredCalls = useMemo(() => {
    return calls.filter((call) => {
      const matchesSearch =
        call.agentName.toLowerCase().includes(debouncedSearchQuery.toLowerCase()) ||
        call.phoneNumber.includes(debouncedSearchQuery);
      const matchesStatus =
        statusFilter === "all" ||
        call.status === statusFilter ||
        (statusFilter === "inbound" && call.direction === "inbound") ||
        (statusFilter === "outbound" && call.direction === "outbound");
      return matchesSearch && matchesStatus;
    });
  }, [calls, debouncedSearchQuery, statusFilter]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Call History</h1>
        <p className="text-muted-foreground">View and analyze your voice agent call logs</p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Recent Calls</CardTitle>
              <CardDescription>
                {filteredCalls.length === 0
                  ? "No calls yet"
                  : `${filteredCalls.length} calls found`}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Input
                placeholder="Search calls..."
                className="w-[250px]"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Calls</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                  <SelectItem value="inbound">Inbound</SelectItem>
                  <SelectItem value="outbound">Outbound</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {calls.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <History className="mb-4 h-16 w-16 text-muted-foreground/50" />
              <h3 className="mb-2 text-lg font-semibold">No calls yet</h3>
              <p className="max-w-sm text-center text-sm text-muted-foreground">
                Call history will appear here once your voice agents start handling calls
              </p>
            </div>
          ) : filteredCalls.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
              <History className="mb-4 h-16 w-16 text-muted-foreground/50" />
              <h3 className="mb-2 text-lg font-semibold">No matching calls found</h3>
              <p className="max-w-sm text-center text-sm text-muted-foreground">
                Try adjusting your search or filter criteria
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date & Time</TableHead>
                  <TableHead>Agent</TableHead>
                  <TableHead>Direction</TableHead>
                  <TableHead>From/To</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[100px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCalls.map((call) => (
                  <TableRow key={call.id}>
                    <TableCell className="text-sm">
                      {new Date(call.timestamp).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-medium">{call.agentName}</TableCell>
                    <TableCell>
                      <Badge variant={call.direction === "inbound" ? "default" : "secondary"}>
                        {call.direction}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{call.phoneNumber}</TableCell>
                    <TableCell>{call.duration}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          call.status === "completed"
                            ? "default"
                            : call.status === "failed"
                              ? "destructive"
                              : "secondary"
                        }
                      >
                        {call.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        {call.recordingUrl && (
                          <Button variant="ghost" size="icon" title="Play recording">
                            <Play className="h-4 w-4" />
                          </Button>
                        )}
                        {call.transcriptUrl && (
                          <Button variant="ghost" size="icon" title="Download transcript">
                            <Download className="h-4 w-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
