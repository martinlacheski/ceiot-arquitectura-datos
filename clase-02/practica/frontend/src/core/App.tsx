import { useEffect, useState } from "react";

import { Badge } from "../components/ui/badge";
import { ConfirmDialog } from "../components/custom/ConfirmDialog";
import { Button } from "../components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ResourcePanel } from "../modules/resources/ResourcePanel";
import {
  isResourceEndpoint,
  resources,
  type ResourceEndpoint,
} from "../modules/resources/catalog";
import { requestHealth } from "../shared/api/client";

function resourceFromUrl(): ResourceEndpoint {
  const value = new URLSearchParams(window.location.search).get("resource");
  return isResourceEndpoint(value) ? value : "organizations";
}

export function App() {
  const [activeResource, setActiveResource] =
    useState<ResourceEndpoint>(resourceFromUrl);
  const [apiAvailable, setApiAvailable] = useState<boolean | null>(null);
  const resource =
    resources.find((item) => item.endpoint === activeResource) ?? resources[0];
  async function checkHealth() {
    setApiAvailable(await requestHealth());
  }
  useEffect(() => {
    void checkHealth();
    const onPopState = () => setActiveResource(resourceFromUrl());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);
  function selectResource(endpoint: string | null) {
    if (isResourceEndpoint(endpoint)) {
      window.history.pushState({}, "", `?resource=${endpoint}`);
      setActiveResource(endpoint);
    }
  }
  return (
    <main className="min-h-screen bg-background">
      <header className="border-b bg-card">
        <div className="mx-auto flex w-[min(100%-2rem,1500px)] flex-col gap-5 py-5">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
            <div className="flex items-center gap-3">
              <Badge className="size-9 justify-center">C2</Badge>
              <div>
                <p className="text-sm text-muted-foreground">
                  Arquitectura de datos
                </p>
                <h1 className="font-heading text-xl font-semibold">
                  Práctica IoT
                </h1>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <Badge
                variant={apiAvailable === false ? "destructive" : "secondary"}
              >
                {apiAvailable === null
                  ? "Comprobando API"
                  : apiAvailable
                    ? "API y base disponibles"
                    : "API no disponible"}
              </Badge>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void checkHealth()}
              >
                Actualizar
              </Button>
            </div>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">Clase 2</p>
            <h2 className="font-heading text-2xl font-semibold tracking-tight">
              Modelo de datos IoT
            </h2>
          </div>
          <Tabs value={activeResource} onValueChange={selectResource}>
            <TabsList
              variant="line"
              aria-label="Recursos del modelo IoT"
              className="max-w-full overflow-x-auto"
            >
              <>
                {resources.map((item) => (
                  <TabsTrigger
                    key={item.endpoint}
                    id={`tab-${item.endpoint}`}
                    value={item.endpoint}
                    onClick={(event) => event.currentTarget.focus()}
                  >
                    {item.title}
                  </TabsTrigger>
                ))}
              </>
            </TabsList>
          </Tabs>
        </div>
      </header>
      <ResourcePanel resource={resource} />
      <ConfirmDialog />
    </main>
  );
}
