import { useEffect, useMemo } from "react";

import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { DataTablePagination } from "../../components-data-table-pagination/DataTablePagination";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "../../components/ui/empty";
import { Skeleton } from "../../components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import type { ApiItem } from "../../shared/api/client";
import type { MeasurementFilters, ResourceDefinition } from "./catalog";

function itemValue(item: ApiItem, field: string): string {
  const value = item[field];
  if (value === null || value === undefined || value === "") return "—";
  if (field.endsWith("_at")) {
    return new Intl.DateTimeFormat("es-AR", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(String(value)));
  }
  return String(value);
}

function calendarDate(value: unknown): string | undefined {
  const date = String(value ?? "").match(/^\d{4}-\d{2}-\d{2}/)?.[0];
  return date;
}

function measurementMatches(
  measurement: ApiItem,
  devicesById: Map<string, ApiItem>,
  filters: MeasurementFilters,
): boolean {
  const device = devicesById.get(String(measurement.device_id));
  const recordedAt = calendarDate(measurement.recorded_at);

  return (
    (!filters.organizationId ||
      String(device?.organization_id) === filters.organizationId) &&
    (!filters.locationId ||
      String(device?.current_location_id) === filters.locationId) &&
    (!filters.deviceId || String(measurement.device_id) === filters.deviceId) &&
    (!filters.recordedFrom ||
      (recordedAt !== undefined && recordedAt >= filters.recordedFrom)) &&
    (!filters.recordedTo ||
      (recordedAt !== undefined && recordedAt <= filters.recordedTo))
  );
}

export function ResourceTable({
  resource,
  items,
  search,
  relationshipFilter,
  measurementFilters = {},
  devices = [],
}: {
  resource: ResourceDefinition;
  items: ApiItem[];
  search: string;
  relationshipFilter?: string;
  measurementFilters?: MeasurementFilters;
  devices?: ApiItem[];
}) {
  const invalidDateRange = Boolean(
    measurementFilters.recordedFrom &&
      measurementFilters.recordedTo &&
      measurementFilters.recordedFrom > measurementFilters.recordedTo,
  );
  const devicesById = useMemo(
    () => new Map(devices.map((device) => [String(device.id), device])),
    [devices],
  );
  const filteredItems = useMemo(() => {
    if (resource.endpoint === "measurements") {
      if (invalidDateRange) return [];
      return items.filter((item) =>
        measurementMatches(item, devicesById, measurementFilters),
      );
    }
    return items.filter(
      (item) =>
        !relationshipFilter ||
        String(item.organization_id ?? item.device_id) === relationshipFilter,
    );
  }, [
    devicesById,
    invalidDateRange,
    items,
    measurementFilters,
    relationshipFilter,
    resource.endpoint,
  ]);
  const columns: ColumnDef<ApiItem>[] = resource.columns.map((column) => ({
    id: column.name,
    accessorFn: (item) => itemValue(item, column.name),
    header: column.label,
    cell: ({ getValue }) => String(getValue() ?? "—"),
  }));
  const table = useReactTable({
    data: filteredItems,
    columns,
    state: { globalFilter: search },
    globalFilterFn: (row, _columnId, filter) =>
      Object.values(row.original).some((value) =>
        String(value ?? "")
          .toLocaleLowerCase("es-AR")
          .includes(String(filter).toLocaleLowerCase("es-AR")),
      ),
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 10 } },
  });

  useEffect(() => {
    table.setPageIndex(0);
  }, [
    measurementFilters.deviceId,
    measurementFilters.locationId,
    measurementFilters.organizationId,
    measurementFilters.recordedFrom,
    measurementFilters.recordedTo,
    relationshipFilter,
    search,
    table,
  ]);

  const rows = table.getRowModel().rows;
  if (items.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Aún no hay {resource.title.toLowerCase()}</EmptyTitle>
          <EmptyDescription>
            Use la acción Nuevo para abrir el modal y crear el primer registro
            de este recurso.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {rows.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyTitle>No hay resultados</EmptyTitle>
            <EmptyDescription>
              Pruebe con otra búsqueda o limpie los filtros.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext(),
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <DataTablePagination
        table={table}
        totalItems={filteredItems.length}
        entityName={resource.title.toLowerCase()}
      />
    </div>
  );
}

export function ResourceTableSkeleton() {
  return (
    <div
      className="flex flex-col gap-3"
      aria-label="Cargando registros"
      aria-busy="true"
    >
      {Array.from({ length: 4 }, (_, index) => (
        <Skeleton key={index} className="h-10 w-full" />
      ))}
    </div>
  );
}
