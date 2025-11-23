"use client";

import React from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Check, Zap, TrendingUp, Crown } from "lucide-react";
import { PRICING_TIERS } from "@/lib/pricing-tiers";
import { cn } from "@/lib/utils";

interface TierSelectorProps {
  selectedTier: string;
  onTierChange: (tierId: string) => void;
}

const tierIcons = {
  budget: Zap,
  balanced: TrendingUp,
  premium: Crown,
};

export const TierSelector = React.memo(function TierSelector({
  selectedTier,
  onTierChange,
}: TierSelectorProps) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {PRICING_TIERS.map((tier) => {
        const Icon = tierIcons[tier.id as keyof typeof tierIcons];
        const isSelected = selectedTier === tier.id;

        return (
          <Card
            key={tier.id}
            className={cn(
              "cursor-pointer transition-all hover:shadow-lg",
              isSelected && "shadow-lg ring-2 ring-primary"
            )}
            onClick={() => onTierChange(tier.id)}
          >
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-lg",
                      tier.id === "budget" && "bg-green-500/10 text-green-600",
                      tier.id === "balanced" && "bg-blue-500/10 text-blue-600",
                      tier.id === "premium" && "bg-purple-500/10 text-purple-600"
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <CardTitle className="text-lg">{tier.name}</CardTitle>
                    {tier.recommended && (
                      <Badge variant="default" className="mt-1 text-xs">
                        Recommended
                      </Badge>
                    )}
                  </div>
                </div>
                {isSelected && (
                  <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary">
                    <Check className="h-4 w-4 text-primary-foreground" />
                  </div>
                )}
              </div>
              <CardDescription className="mt-2">{tier.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-3xl font-bold">${tier.costPerHour.toFixed(2)}</span>
                  <span className="text-sm text-muted-foreground">/hour</span>
                </div>
                <div className="text-xs text-muted-foreground">
                  ${tier.costPerMinute.toFixed(4)}/min
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium">Performance:</div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Latency:</span>
                    <div className="font-medium">{tier.performance.latency}</div>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Speed:</span>
                    <div className="font-medium">{tier.performance.speed}</div>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium">Includes:</div>
                <ul className="space-y-1">
                  {tier.features.slice(0, 3).map((feature, index) => (
                    <li key={index} className="flex items-start gap-2 text-xs">
                      <Check className="mt-0.5 h-3 w-3 flex-shrink-0 text-green-600" />
                      <span className="text-muted-foreground">{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="border-t pt-2">
                <div className="space-y-1 text-xs">
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">LLM:</span>
                    <span className="font-mono font-medium">{tier.config.llmModel}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">STT:</span>
                    <span className="font-mono font-medium">{tier.config.sttModel}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">TTS:</span>
                    <span className="font-mono font-medium">{tier.config.ttsModel}</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
});

export function TierComparison({
  callsPerMonth = 1000,
  avgMinutes = 5,
}: {
  callsPerMonth?: number;
  avgMinutes?: number;
}) {
  const totalMinutes = callsPerMonth * avgMinutes;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Cost Comparison</CardTitle>
        <CardDescription>
          Estimated monthly costs for {callsPerMonth.toLocaleString()} calls ({avgMinutes} min avg)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {PRICING_TIERS.map((tier) => {
            const monthlyCost = (totalMinutes * tier.costPerMinute).toFixed(2);
            const premiumCost = totalMinutes * 0.032;
            const savings = premiumCost - totalMinutes * tier.costPerMinute;
            const savingsPercent = ((savings / premiumCost) * 100).toFixed(0);

            return (
              <div
                key={tier.id}
                className="flex items-center justify-between rounded-lg border p-3"
              >
                <div className="flex items-center gap-3">
                  <div className="font-medium">{tier.name}</div>
                  {tier.recommended && (
                    <Badge variant="default" className="text-xs">
                      Best Value
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="font-bold">${monthlyCost}/mo</div>
                    {tier.id !== "premium" && (
                      <div className="text-xs text-green-600 dark:text-green-400">
                        Save ${savings.toFixed(2)} ({savingsPercent}%)
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-4 rounded-lg bg-muted/50 p-4 text-sm">
          <div className="mb-2 font-medium">Example Annual Savings:</div>
          <div className="space-y-1 text-xs text-muted-foreground">
            <div>• 10K calls/month: Save up to $15,000/year</div>
            <div>• 100K calls/month: Save up to $150,000/year</div>
            <div>• 1M calls/month: Save up to $1.5M/year</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
