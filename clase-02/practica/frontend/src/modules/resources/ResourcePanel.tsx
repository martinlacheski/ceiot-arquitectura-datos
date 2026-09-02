import { useEffect, useState } from "react";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../../components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import type { MeasurementFilters, ResourceDefinition } from "./catalog";
import { ResourceFeedback } from "./ResourceFeedback";
import { ResourceForm } from "./ResourceForm";
import { ResourceTable, ResourceTableSkeleton } from "./ResourceTable";
import { ResourceToolbar } from "./ResourceToolbar";
import { useResourceData } from "./useResourceData";

export function ResourcePanel({ resource }: { resource: ResourceDefinition }) {
  const { items, related, loading, submitting, error, success, load, create } =
    useResourceData(resource);
  const [search, setSearch] = useState("");
  const [relationshipFilter, setRelationshipFilter] = useState<string>();
  const [measurementFilters, setMeasurementFilters] =
    useState<MeasurementFilters>({});
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  useEffect(() => {
    setSearch("");
    setRelationshipFilter(undefined);
    setMeasurementFilters({});
    setCreateDialogOpen(false);
  }, [resource.endpoint]);

  const filterOptions =
    resource.endpoint === "measurements"
      ? (related.devices ?? [])
      : (related.organizations ?? []);

  return (
    <section
      className="mx-auto flex w-[min(100%-2rem,1500px)] flex-col gap-6 py-6 md:py-10"
      role="tabpanel"
      id={`panel-${resource.endpoint}`}
      aria-labelledby={`tab-${resource.endpoint}`}
    >
      <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div className="flex flex-col gap-1">
          <Badge variant="outline" className="w-fit">
            Recurso del modelo
          </Badge>
          <h2 className="font-heading text-2xl font-semibold tracking-tight">
            {resource.title}
          </h2>
          <p className="max-w-2xl text-sm text-muted-foreground">
            {resource.description}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => void load()}
          disabled={loading}
        >
          Actualizar registros
        </Button>
      </div>
      <ResourceFeedback
        error={error}
        success={success}
        onRetry={() => void load()}
      />
      <Card>
        <CardHeader>
          <CardTitle>Registros</CardTitle>
          <CardDescription>
            {loading ? "Actualizando registros" : `${items.length} en total`}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ResourceToolbar
            resource={resource}
            related={filterOptions}
            search={search}
            onSearchChange={setSearch}
            relationshipFilter={relationshipFilter}
            onRelationshipFilterChange={setRelationshipFilter}
            measurementFilters={measurementFilters}
            onMeasurementFiltersChange={setMeasurementFilters}
            onCreate={() => setCreateDialogOpen(true)}
          />
          {loading ? (
            <ResourceTableSkeleton />
          ) : (
            <ResourceTable
              resource={resource}
              items={items}
              search={search}
              relationshipFilter={relationshipFilter}
              measurementFilters={measurementFilters}
              devices={related.devices ?? []}
            />
          )}
        </CardContent>
      </Card>
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{resource.createLabel}</DialogTitle>
            <DialogDescription>
              Complete los campos para registrar una nueva entidad.
            </DialogDescription>
          </DialogHeader>
          <ResourceForm
            key={resource.endpoint}
            resource={resource}
            related={related}
            submitting={submitting}
            onCreate={create}
            onSuccess={() => setCreateDialogOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </section>
  );
}
