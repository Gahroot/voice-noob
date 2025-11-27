"use client";

import { useState, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import * as z from "zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { createAgent, type CreateAgentRequest } from "@/lib/api/agents";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { PRICING_TIERS } from "@/lib/pricing-tiers";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Sparkles,
  Zap,
  Crown,
  Bot,
  MessageSquare,
  Wrench,
  Settings,
  Play,
} from "lucide-react";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { cn } from "@/lib/utils";

// OpenAI Realtime API voices (only for Premium tier)
const REALTIME_VOICES = [
  { id: "alloy", name: "Alloy", description: "Neutral and balanced" },
  { id: "ash", name: "Ash", description: "Clear and precise" },
  { id: "ballad", name: "Ballad", description: "Melodic and smooth" },
  { id: "coral", name: "Coral", description: "Warm and friendly" },
  { id: "echo", name: "Echo", description: "Resonant and deep" },
  { id: "sage", name: "Sage", description: "Calm and thoughtful" },
  { id: "shimmer", name: "Shimmer", description: "Bright and energetic" },
  { id: "verse", name: "Verse", description: "Versatile and expressive" },
] as const;

// Tool configurations
const AVAILABLE_TOOLS = [
  {
    id: "crm",
    name: "Internal CRM",
    desc: "Search customers, view contacts, manage customer data",
    connected: true,
  },
  {
    id: "bookings",
    name: "Appointment Booking",
    desc: "Check availability, book/cancel/reschedule appointments",
    connected: true,
  },
] as const;

const WIZARD_STEPS = [
  { id: 1, label: "Pricing", icon: Sparkles },
  { id: 2, label: "Basics", icon: Bot },
  { id: 3, label: "Prompt", icon: MessageSquare },
  { id: 4, label: "Tools", icon: Wrench },
  { id: 5, label: "Settings", icon: Settings },
] as const;

const agentFormSchema = z.object({
  pricingTier: z.enum(["budget", "balanced", "premium"]).default("balanced"),
  name: z.string().min(2, "Name must be at least 2 characters"),
  description: z.string().optional(),
  language: z.string().default("en-US"),
  voice: z.string().default("shimmer"),
  systemPrompt: z.string().min(10, "System prompt is required"),
  enabledTools: z.array(z.string()).default([]),
  phoneNumberId: z.string().optional(),
  enableRecording: z.boolean().default(true),
  enableTranscript: z.boolean().default(true),
});

type AgentFormValues = z.infer<typeof agentFormSchema>;

export default function CreateAgentPage() {
  const [step, setStep] = useState(1);
  const router = useRouter();

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    defaultValues: {
      name: "",
      description: "",
      systemPrompt: "",
      pricingTier: "balanced",
      language: "en-US",
      voice: "shimmer",
      enabledTools: [],
      phoneNumberId: "",
      enableRecording: true,
      enableTranscript: true,
    },
  });

  const pricingTier = useWatch({ control: form.control, name: "pricingTier" });
  const enabledTools = useWatch({ control: form.control, name: "enabledTools" });
  const agentName = useWatch({ control: form.control, name: "name" });
  const systemPrompt = useWatch({ control: form.control, name: "systemPrompt" });

  const selectedTier = useMemo(
    () => PRICING_TIERS.find((t) => t.id === pricingTier),
    [pricingTier]
  );

  const createAgentMutation = useMutation({
    mutationFn: createAgent,
    onSuccess: (agent) => {
      toast.success(`Agent "${agent.name}" created successfully!`);
      router.push("/dashboard/agents");
    },
    onError: (error: Error) => {
      toast.error(`Failed to create agent: ${error.message}`);
    },
  });

  function onSubmit(data: AgentFormValues) {
    const request: CreateAgentRequest = {
      name: data.name,
      description: data.description,
      pricing_tier: data.pricingTier,
      system_prompt: data.systemPrompt,
      language: data.language,
      voice: data.pricingTier === "premium" ? data.voice : undefined,
      enabled_tools: data.enabledTools,
      phone_number_id: data.phoneNumberId,
      enable_recording: data.enableRecording,
      enable_transcript: data.enableTranscript,
    };
    createAgentMutation.mutate(request);
  }

  const validateStep = async (currentStep: number): Promise<boolean> => {
    switch (currentStep) {
      case 1:
        return true; // Pricing tier always has a default
      case 2:
        return form.trigger("name");
      case 3:
        return form.trigger("systemPrompt");
      case 4:
        return true; // Tools are optional
      case 5:
        return true; // Settings have defaults
      default:
        return true;
    }
  };

  const handleNext = async () => {
    const isValid = await validateStep(step);
    if (isValid && step < 5) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

  const getTierIcon = (tierId: string) => {
    switch (tierId) {
      case "budget":
        return Zap;
      case "balanced":
        return Sparkles;
      case "premium":
        return Crown;
      default:
        return Sparkles;
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8" asChild>
          <Link href="/dashboard/agents">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-xl font-semibold">Create Voice Agent</h1>
          <p className="text-sm text-muted-foreground">
            Step {step} of 5 &middot; {WIZARD_STEPS[step - 1]?.label ?? ""}
          </p>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="flex items-center gap-1">
        {WIZARD_STEPS.map((s, idx) => {
          const Icon = s.icon;
          const isActive = s.id === step;
          const isCompleted = s.id < step;

          return (
            <div key={s.id} className="flex flex-1 items-center">
              <button
                type="button"
                onClick={() => s.id < step && setStep(s.id)}
                disabled={s.id > step}
                className={cn(
                  "flex flex-1 items-center gap-2 rounded-lg border p-2 transition-all",
                  isActive && "border-primary bg-primary/5 ring-1 ring-primary",
                  isCompleted &&
                    "cursor-pointer border-primary/50 bg-primary/5 hover:bg-primary/10",
                  !isActive && !isCompleted && "cursor-not-allowed border-border bg-muted/30"
                )}
              >
                <div
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium",
                    isActive && "bg-primary text-primary-foreground",
                    isCompleted && "bg-primary text-primary-foreground",
                    !isActive && !isCompleted && "bg-muted text-muted-foreground"
                  )}
                >
                  {isCompleted ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Icon className="h-3.5 w-3.5" />
                  )}
                </div>
                <span
                  className={cn(
                    "hidden text-xs font-medium sm:block",
                    isActive && "text-foreground",
                    isCompleted && "text-foreground",
                    !isActive && !isCompleted && "text-muted-foreground"
                  )}
                >
                  {s.label}
                </span>
              </button>
              {idx < WIZARD_STEPS.length - 1 && (
                <div
                  className={cn(
                    "mx-1 h-0.5 w-4 rounded-full",
                    isCompleted ? "bg-primary" : "bg-border"
                  )}
                />
              )}
            </div>
          );
        })}
      </div>

      <Form {...form}>
        <form
          onSubmit={(e) => {
            void form.handleSubmit(onSubmit)(e);
          }}
        >
          {/* Step 1: Pricing Tier */}
          {step === 1 && (
            <Card>
              <CardContent className="p-6">
                <div className="mb-4">
                  <h2 className="text-lg font-medium">Choose Your Pricing Tier</h2>
                  <p className="text-sm text-muted-foreground">
                    Select the right balance of cost and quality for your use case
                  </p>
                </div>

                <div className="grid gap-3 md:grid-cols-3">
                  {PRICING_TIERS.map((tier) => {
                    const TierIcon = getTierIcon(tier.id);
                    const isSelected = pricingTier === tier.id;

                    return (
                      <button
                        key={tier.id}
                        type="button"
                        onClick={() =>
                          form.setValue("pricingTier", tier.id as "budget" | "balanced" | "premium")
                        }
                        className={cn(
                          "relative flex flex-col rounded-lg border p-4 text-left transition-all hover:border-primary/50",
                          isSelected && "border-primary bg-primary/5 ring-2 ring-primary"
                        )}
                      >
                        {tier.id === "balanced" && (
                          <Badge className="absolute -top-2 right-3 text-[10px]">Popular</Badge>
                        )}
                        <div className="mb-3 flex items-center gap-2">
                          <div
                            className={cn(
                              "flex h-8 w-8 items-center justify-center rounded-md",
                              isSelected ? "bg-primary text-primary-foreground" : "bg-muted"
                            )}
                          >
                            <TierIcon className="h-4 w-4" />
                          </div>
                          <div>
                            <div className="font-medium">{tier.name}</div>
                            <div className="text-xs text-muted-foreground">
                              ${tier.costPerHour.toFixed(2)}/hr
                            </div>
                          </div>
                        </div>
                        <p className="mb-3 text-xs text-muted-foreground">{tier.description}</p>
                        <div className="space-y-1 text-xs">
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Speed</span>
                            <span className="font-medium">{tier.performance.speed}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Quality</span>
                            <span className="font-medium">{tier.performance.quality}</span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-muted-foreground">Model</span>
                            <span className="font-mono text-[10px]">{tier.config.llmModel}</span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 2: Basic Info */}
          {step === 2 && (
            <Card>
              <CardContent className="space-y-4 p-6">
                <div className="mb-2">
                  <h2 className="text-lg font-medium">Basic Information</h2>
                  <p className="text-sm text-muted-foreground">
                    Give your agent a name and identity
                  </p>
                </div>

                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Agent Name *</FormLabel>
                      <FormControl>
                        <Input placeholder="Customer Support Agent" {...field} />
                      </FormControl>
                      <FormDescription>A friendly name to identify your agent</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Description</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Handles customer inquiries and support requests..."
                          className="min-h-[80px]"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>Optional description for your reference</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid gap-4 md:grid-cols-2">
                  <FormField
                    control={form.control}
                    name="language"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Language</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="en-US">English (US)</SelectItem>
                            <SelectItem value="en-GB">English (UK)</SelectItem>
                            <SelectItem value="es-ES">Spanish</SelectItem>
                            <SelectItem value="fr-FR">French</SelectItem>
                            <SelectItem value="de-DE">German</SelectItem>
                            <SelectItem value="ja-JP">Japanese</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  {pricingTier === "premium" && (
                    <FormField
                      control={form.control}
                      name="voice"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Voice</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select voice" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {REALTIME_VOICES.map((voice) => (
                                <SelectItem key={voice.id} value={voice.id}>
                                  {voice.name} - {voice.description}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 3: System Prompt */}
          {step === 3 && (
            <Card>
              <CardContent className="space-y-4 p-6">
                <div className="mb-2">
                  <h2 className="flex items-center gap-2 text-lg font-medium">
                    System Prompt
                    <InfoTooltip content="The system prompt defines how your agent behaves. Include its role, personality, guidelines, and any rules it should follow. This is the most important setting." />
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Define your agent&apos;s personality and behavior
                  </p>
                </div>

                <FormField
                  control={form.control}
                  name="systemPrompt"
                  render={({ field }) => {
                    const charCount = field.value?.length ?? 0;
                    const isOptimal = charCount >= 100 && charCount <= 2000;
                    const isTooShort = charCount > 0 && charCount < 100;

                    return (
                      <FormItem>
                        <div className="flex items-center justify-between">
                          <FormLabel>Instructions *</FormLabel>
                          <span
                            className={cn(
                              "text-xs",
                              isOptimal && "text-green-600",
                              isTooShort && "text-yellow-600"
                            )}
                          >
                            {charCount} characters
                            {isTooShort && " (aim for 100+)"}
                          </span>
                        </div>
                        <FormControl>
                          <Textarea
                            placeholder={`You are a helpful customer support agent for [Company Name].

Your role:
- Answer questions about our products and services
- Help customers troubleshoot issues
- Be polite, professional, and concise

Guidelines:
- Keep responses brief and to the point
- If you don't know something, say so honestly
- Always offer to escalate to a human if needed`}
                            className="min-h-[240px] font-mono text-sm"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          Tell your agent who they are, how to behave, and what rules to follow
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    );
                  }}
                />
              </CardContent>
            </Card>
          )}

          {/* Step 4: Tools */}
          {step === 4 && (
            <Card>
              <CardContent className="space-y-4 p-6">
                <div className="mb-2">
                  <h2 className="flex items-center gap-2 text-lg font-medium">
                    Tools & Integrations
                    <InfoTooltip content="Tools give your agent abilities like looking up customer info or booking appointments. Enable tools your agent needs to help callers." />
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Enable integrations for your agent (optional)
                  </p>
                </div>

                <div className="grid gap-3 md:grid-cols-2">
                  {AVAILABLE_TOOLS.map((tool) => (
                    <FormField
                      key={tool.id}
                      control={form.control}
                      name="enabledTools"
                      render={({ field }) => {
                        const isChecked = field.value?.includes(tool.id);
                        const handleToggle = () => {
                          if (!tool.connected) return;
                          const current = field.value || [];
                          field.onChange(
                            isChecked ? current.filter((v) => v !== tool.id) : [...current, tool.id]
                          );
                        };

                        return (
                          <FormItem
                            className={cn(
                              "flex flex-row items-start space-x-3 space-y-0 rounded-lg border p-4 transition-all",
                              tool.connected
                                ? "cursor-pointer hover:bg-accent"
                                : "cursor-not-allowed opacity-60",
                              isChecked && "border-primary bg-primary/5"
                            )}
                            onClick={handleToggle}
                          >
                            <FormControl>
                              <input
                                type="checkbox"
                                className="mt-0.5 h-4 w-4 cursor-pointer"
                                checked={isChecked}
                                onChange={() => {}}
                                disabled={!tool.connected}
                              />
                            </FormControl>
                            <div className="pointer-events-none flex-1 space-y-1">
                              <div className="flex items-center justify-between gap-2">
                                <FormLabel className="font-medium">{tool.name}</FormLabel>
                                <Badge variant="outline" className="text-[10px]">
                                  Built-in
                                </Badge>
                              </div>
                              <FormDescription className="text-xs">{tool.desc}</FormDescription>
                            </div>
                          </FormItem>
                        );
                      }}
                    />
                  ))}
                </div>

                <div className="rounded-lg border border-dashed p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">Need more integrations?</p>
                      <p className="text-xs text-muted-foreground">
                        Connect Google Calendar, Salesforce, HubSpot and more
                      </p>
                    </div>
                    <Button variant="outline" size="sm" asChild>
                      <Link href="/dashboard/integrations" target="_blank">
                        Manage Integrations
                      </Link>
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Step 5: Settings & Review */}
          {step === 5 && (
            <div className="space-y-4">
              <Card>
                <CardContent className="space-y-4 p-6">
                  <div className="mb-2">
                    <h2 className="text-lg font-medium">Call Settings</h2>
                    <p className="text-sm text-muted-foreground">
                      Configure recording and transcription
                    </p>
                  </div>

                  <FormField
                    control={form.control}
                    name="enableRecording"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel className="text-sm font-medium">Call Recording</FormLabel>
                          <FormDescription className="text-xs">
                            Record all calls for quality assurance
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="enableTranscript"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel className="text-sm font-medium">Transcripts</FormLabel>
                          <FormDescription className="text-xs">
                            Save searchable conversation transcripts
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              {/* Summary Card */}
              <Card className="border-primary/30 bg-primary/5">
                <CardContent className="p-6">
                  <h2 className="mb-4 text-lg font-medium">Review Your Agent</h2>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-3">
                      <div>
                        <p className="text-xs text-muted-foreground">Name</p>
                        <p className="font-medium">{agentName || "Not set"}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Pricing Tier</p>
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{selectedTier?.name}</span>
                          <Badge variant="outline" className="text-[10px]">
                            ${selectedTier?.costPerHour.toFixed(2)}/hr
                          </Badge>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">AI Model</p>
                        <p className="font-mono text-sm">{selectedTier?.config.llmModel}</p>
                      </div>
                    </div>

                    <div className="space-y-3">
                      <div>
                        <p className="text-xs text-muted-foreground">System Prompt</p>
                        <p className="text-sm">
                          {systemPrompt
                            ? `${systemPrompt.slice(0, 80)}${systemPrompt.length > 80 ? "..." : ""}`
                            : "Not set"}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Tools Enabled</p>
                        <p className="font-medium">
                          {enabledTools.length > 0
                            ? `${enabledTools.length} tool${enabledTools.length > 1 ? "s" : ""}`
                            : "None"}
                        </p>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Navigation */}
          <div className="mt-6 flex items-center justify-between">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={handleBack}
              disabled={step === 1}
            >
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back
            </Button>

            {step < 5 ? (
              <Button type="button" size="sm" onClick={() => void handleNext()}>
                Next
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            ) : (
              <Button type="submit" size="sm" disabled={createAgentMutation.isPending}>
                <Play className="mr-2 h-4 w-4" />
                {createAgentMutation.isPending ? "Creating..." : "Create Agent"}
              </Button>
            )}
          </div>
        </form>
      </Form>
    </div>
  );
}
