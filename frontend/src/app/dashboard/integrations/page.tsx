"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Search, Check, Settings as SettingsIcon, Zap } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AVAILABLE_INTEGRATIONS, type Integration } from "@/lib/integrations";
import Image from "next/image";

export default function IntegrationsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  // Mock connected integrations - will be replaced with API
  const connectedIntegrations = new Set<string>([]);

  const categories = [
    { value: "all", label: "All" },
    { value: "crm", label: "CRM" },
    { value: "calendar", label: "Calendar" },
    { value: "database", label: "Database" },
    { value: "communication", label: "Communication" },
    { value: "productivity", label: "Productivity" },
    { value: "other", label: "Other" },
  ];

  const filteredIntegrations = AVAILABLE_INTEGRATIONS.filter((integration) => {
    const matchesSearch =
      integration.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      integration.description.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory =
      selectedCategory === "all" || integration.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const connectedCount = Array.from(connectedIntegrations).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Integrations & Tools</h1>
        <p className="text-muted-foreground">
          Connect external services for your voice agents to use
        </p>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="font-normal">
            {connectedCount} Connected
          </Badge>
          <Badge variant="outline" className="font-normal">
            {AVAILABLE_INTEGRATIONS.length} Available
          </Badge>
        </div>
        <div className="relative w-[300px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search integrations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
          />
        </div>
      </div>

      <Tabs defaultValue="all" onValueChange={setSelectedCategory}>
        <TabsList>
          {categories.map((cat) => (
            <TabsTrigger key={cat.value} value={cat.value}>
              {cat.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value={selectedCategory} className="mt-6">
          {filteredIntegrations.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16">
                <Zap className="h-16 w-16 text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-semibold mb-2">No integrations found</h3>
                <p className="text-sm text-muted-foreground">
                  Try adjusting your search or category filter
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredIntegrations.map((integration) => (
                <IntegrationCard
                  key={integration.id}
                  integration={integration}
                  isConnected={connectedIntegrations.has(integration.id)}
                />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function IntegrationCard({
  integration,
  isConnected,
}: {
  integration: Integration;
  isConnected: boolean;
}) {
  const [isConfigDialogOpen, setIsConfigDialogOpen] = useState(false);

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center overflow-hidden">
              {integration.icon ? (
                <Image
                  src={integration.icon}
                  alt={integration.name}
                  width={24}
                  height={24}
                />
              ) : (
                <Zap className="h-5 w-5" />
              )}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">{integration.name}</CardTitle>
                {integration.isPopular && (
                  <Badge variant="secondary" className="text-xs">
                    Popular
                  </Badge>
                )}
              </div>
              <CardDescription className="text-xs mt-1">
                {integration.category.toUpperCase()}
              </CardDescription>
            </div>
          </div>
          {isConnected && (
            <Check className="h-5 w-5 text-green-600 dark:text-green-400" />
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground mb-4 line-clamp-2">
          {integration.description}
        </p>
        <div className="flex gap-2">
          <Dialog open={isConfigDialogOpen} onOpenChange={setIsConfigDialogOpen}>
            <DialogTrigger asChild>
              <Button
                variant={isConnected ? "outline" : "default"}
                className="flex-1"
                size="sm"
              >
                {isConnected ? (
                  <>
                    <SettingsIcon className="mr-2 h-3 w-3" />
                    Configure
                  </>
                ) : (
                  "Connect"
                )}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md">
              <DialogHeader>
                <DialogTitle>Connect {integration.name}</DialogTitle>
                <DialogDescription>
                  {integration.authType === "oauth"
                    ? "Click Connect to authorize access via OAuth"
                    : "Enter your API credentials below"}
                </DialogDescription>
              </DialogHeader>
              <IntegrationConfigForm
                integration={integration}
                isConnected={isConnected}
                onClose={() => setIsConfigDialogOpen(false)}
              />
            </DialogContent>
          </Dialog>
          {integration.documentationUrl && (
            <Button variant="ghost" size="sm" asChild>
              <a
                href={integration.documentationUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                Docs
              </a>
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function IntegrationConfigForm({
  integration,
  isConnected,
  onClose,
}: {
  integration: Integration;
  isConnected: boolean;
  onClose: () => void;
}) {
  const handleOAuthConnect = async () => {
    // TODO: Implement OAuth flow
    console.log("Starting OAuth for", integration.id);
    // window.location.href = `/api/integrations/${integration.id}/oauth`;
  };

  const handleApiKeySubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const formData = new FormData(e.currentTarget);
    const credentials = Object.fromEntries(formData.entries());
    console.log("Saving credentials for", integration.id, credentials);
    // TODO: API call to save credentials
    onClose();
  };

  const handleDisconnect = () => {
    console.log("Disconnecting", integration.id);
    // TODO: API call to disconnect
    onClose();
  };

  if (integration.authType === "oauth") {
    return (
      <div className="space-y-4">
        {integration.scopes && integration.scopes.length > 0 && (
          <div className="rounded-lg border p-4 space-y-2">
            <p className="text-sm font-medium">This integration will access:</p>
            <ul className="text-sm text-muted-foreground space-y-1">
              {integration.scopes.map((scope) => (
                <li key={scope} className="flex items-center gap-2">
                  <Check className="h-3 w-3" />
                  {scope}
                </li>
              ))}
            </ul>
          </div>
        )}

        {isConnected ? (
          <div className="space-y-4">
            <div className="rounded-lg border border-green-500/20 bg-green-500/10 p-4">
              <div className="flex items-center gap-2 text-green-600 dark:text-green-400">
                <Check className="h-4 w-4" />
                <span className="text-sm font-medium">Connected</span>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={handleOAuthConnect} className="flex-1">
                Reconnect
              </Button>
              <Button variant="destructive" onClick={handleDisconnect} className="flex-1">
                Disconnect
              </Button>
            </div>
          </div>
        ) : (
          <Button onClick={handleOAuthConnect} className="w-full">
            Connect with {integration.name}
          </Button>
        )}
      </div>
    );
  }

  // API Key / Basic Auth Form
  return (
    <form onSubmit={handleApiKeySubmit} className="space-y-4">
      {integration.fields?.map((field) => (
        <div key={field.name} className="space-y-2">
          <label className="text-sm font-medium">
            {field.label}
            {field.required && <span className="text-destructive ml-1">*</span>}
          </label>
          <Input
            name={field.name}
            type={field.type}
            placeholder={field.placeholder}
            required={field.required}
          />
          {field.description && (
            <p className="text-xs text-muted-foreground">{field.description}</p>
          )}
        </div>
      ))}
      <div className="flex gap-2 pt-4">
        {isConnected ? (
          <>
            <Button type="submit" variant="outline" className="flex-1">
              Update
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={handleDisconnect}
              className="flex-1"
            >
              Disconnect
            </Button>
          </>
        ) : (
          <Button type="submit" className="w-full">
            Connect
          </Button>
        )}
      </div>
    </form>
  );
}
