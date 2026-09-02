import { PlusIcon, XIcon } from "lucide-react";

import { ListToolbarLayout } from "../../components-list-toolbar-layout/ListToolbarLayout";
import { SearchableSelect } from "../../components-searchable-select/SearchableSelect";
import { Button } from "../../components/ui/button";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import type { ApiItem } from "../../shared/api/client";
import type { MeasurementFilters, ResourceDefinition } from "./catalog";

function optionLabel(item: ApiItem) {
  return item.serial_number
    ? `${item.name} · ${item.serial_number}`
    : String(item.name ?? item.id);
}

function Search({
  search,
  onSearchChange,
}: {
  search: string;
  onSearchChange: (value: string) => void;
}) {
  return (
    <Input
      aria-label="Buscar registros"
      data-list-toolbar-search-control
      value={search}
      onInput={(event) => onSearchChange(event.currentTarget.value)}
      placeholder="Buscar por cualquier campo"
    />
  );
}

export function applyMeasurementFilter(
  filters: MeasurementFilters,
  filter: "organizationId" | "locationId" | "deviceId",
  value: string | undefined,
): MeasurementFilters {
  if (filter === "organizationId") {
    return {
      ...filters,
      organizationId: value,
      locationId: undefined,
      deviceId: undefined,
    };
  }
  if (filter === "locationId") {
    return { ...filters, locationId: value, deviceId: undefined };
  }
  return { ...filters, deviceId: value };
}

export function measurementFilterOptions(
  devices: ApiItem[],
  filters: MeasurementFilters,
) {
  const organizations = Array.from(
    new Map(
      devices.map((device) => [
        String(device.organization_id),
        {
          value: String(device.organization_id),
          label: String(device.organization_name ?? device.organization_id),
        },
      ]),
    ).values(),
  );
  const locations = devices
    .filter(
      (device) => String(device.organization_id) === filters.organizationId,
    )
    .reduce<{ value: string; label: string }[]>((options, device) => {
      const value = String(device.current_location_id);
      if (!options.some((option) => option.value === value)) {
        options.push({
          value,
          label: String(
            device.current_location_name ?? device.current_location_id,
          ),
        });
      }
      return options;
    }, []);
  const filteredDevices = devices.filter(
    (device) =>
      String(device.organization_id) === filters.organizationId &&
      String(device.current_location_id) === filters.locationId,
  );
  return { organizations, locations, filteredDevices };
}

function MeasurementFilters({
  devices,
  filters,
  onFiltersChange,
}: {
  devices: ApiItem[];
  filters: MeasurementFilters;
  onFiltersChange: (filters: MeasurementFilters) => void;
}) {
  const { organizations, locations, filteredDevices } =
    measurementFilterOptions(devices, filters);

  return (
    <>
      <SearchableSelect
        options={organizations}
        value={filters.organizationId}
        onChange={(organizationId) =>
          onFiltersChange(
            applyMeasurementFilter(filters, "organizationId", organizationId),
          )
        }
        className="w-full md:w-56"
        placeholder="Filtrar por organización"
        searchPlaceholder="Buscar organización"
      />
      <SearchableSelect
        options={locations}
        value={filters.locationId}
        onChange={(locationId) =>
          onFiltersChange(
            applyMeasurementFilter(filters, "locationId", locationId),
          )
        }
        className="w-full md:w-56"
        disabled={!filters.organizationId}
        placeholder={
          filters.organizationId
            ? "Filtrar por ubicación"
            : "Seleccione primero una organización"
        }
        searchPlaceholder="Buscar ubicación"
      />
      <SearchableSelect
        options={filteredDevices.map((device) => ({
          value: String(device.id),
          label: optionLabel(device),
        }))}
        value={filters.deviceId}
        onChange={(deviceId) =>
          onFiltersChange(applyMeasurementFilter(filters, "deviceId", deviceId))
        }
        className="w-full md:w-64"
        disabled={!filters.locationId}
        placeholder={
          filters.locationId
            ? "Filtrar por dispositivo"
            : "Seleccione primero una ubicación"
        }
        searchPlaceholder="Buscar dispositivo"
      />
    </>
  );
}

function MeasurementDateFields({
  filters,
  onFiltersChange,
}: {
  filters: MeasurementFilters;
  onFiltersChange: (filters: MeasurementFilters) => void;
}) {
  const invalidDateRange = Boolean(
    filters.recordedFrom &&
      filters.recordedTo &&
      filters.recordedFrom > filters.recordedTo,
  );

  return (
    <FieldGroup className="w-full gap-3 sm:flex-row lg:w-[30rem] lg:flex-none">
      <Field
        className="gap-1 sm:flex-1"
        data-invalid={invalidDateRange || undefined}
      >
        <FieldLabel htmlFor="measurements-recorded-from">Desde</FieldLabel>
        <Input
          id="measurements-recorded-from"
          type="date"
          className="min-h-11"
          value={filters.recordedFrom ?? ""}
          aria-invalid={invalidDateRange}
          aria-describedby={
            invalidDateRange ? "measurements-date-range-error" : undefined
          }
          onChange={(event) =>
            onFiltersChange({
              ...filters,
              recordedFrom: event.currentTarget.value || undefined,
            })
          }
        />
      </Field>
      <Field
        className="gap-1 sm:flex-1"
        data-invalid={invalidDateRange || undefined}
      >
        <FieldLabel htmlFor="measurements-recorded-to">Hasta</FieldLabel>
        <Input
          id="measurements-recorded-to"
          type="date"
          className="min-h-11"
          value={filters.recordedTo ?? ""}
          aria-invalid={invalidDateRange}
          aria-describedby={
            invalidDateRange ? "measurements-date-range-error" : undefined
          }
          onChange={(event) =>
            onFiltersChange({
              ...filters,
              recordedTo: event.currentTarget.value || undefined,
            })
          }
        />
      </Field>
      {invalidDateRange ? (
        <FieldError id="measurements-date-range-error">
          La fecha desde no puede ser posterior a la fecha hasta.
        </FieldError>
      ) : null}
    </FieldGroup>
  );
}

export function ResourceToolbar({
  resource,
  related,
  search,
  onSearchChange,
  relationshipFilter,
  onRelationshipFilterChange,
  measurementFilters,
  onMeasurementFiltersChange,
  onCreate,
}: {
  resource: ResourceDefinition;
  related: ApiItem[];
  search: string;
  onSearchChange: (value: string) => void;
  relationshipFilter?: string;
  onRelationshipFilterChange: (value?: string) => void;
  measurementFilters?: MeasurementFilters;
  onMeasurementFiltersChange?: (filters: MeasurementFilters) => void;
  onCreate: () => void;
}) {
  const relationship =
    resource.endpoint === "measurements"
      ? undefined
      : resource.endpoint === "organizations"
        ? undefined
        : "Organización";
  const clearFilters = () => {
    onSearchChange("");
    onRelationshipFilterChange(undefined);
    onMeasurementFiltersChange?.({});
  };
  const hasMeasurementFilters = Boolean(
    measurementFilters && Object.values(measurementFilters).some(Boolean),
  );
  const createAction = (
    <Button type="button" onClick={onCreate}>
      <PlusIcon data-icon="inline-start" />
      {resource.createLabel}
    </Button>
  );
  const clearAction = (
    <Button
      type="button"
      variant="ghost"
      disabled={!search && !relationshipFilter && !hasMeasurementFilters}
      onClick={clearFilters}
    >
      <XIcon data-icon="inline-start" />
      Limpiar filtros
    </Button>
  );
  const measurementRows =
    resource.endpoint === "measurements" &&
    measurementFilters &&
    onMeasurementFiltersChange
      ? {
          first: (
            <>
              <div
                className="w-full min-w-0 md:max-w-sm md:flex-1 [&_[data-list-toolbar-search-control]]:min-h-11"
                data-testid="list-toolbar-search"
              >
                <Search search={search} onSearchChange={onSearchChange} />
              </div>
              <MeasurementFilters
                devices={related}
                filters={measurementFilters}
                onFiltersChange={onMeasurementFiltersChange}
              />
            </>
          ),
          second: (
            <div className="flex w-full min-w-0 flex-col gap-3 lg:flex-row lg:flex-nowrap lg:items-end">
              <MeasurementDateFields
                filters={measurementFilters}
                onFiltersChange={onMeasurementFiltersChange}
              />
              <div className="flex shrink-0 flex-wrap items-center gap-2 lg:flex-nowrap">
                {createAction}
                {clearAction}
              </div>
            </div>
          ),
        }
      : undefined;

  return (
    <ListToolbarLayout
      search={<Search search={search} onSearchChange={onSearchChange} />}
      primaryActions={
        <>
          {relationship ? (
            <SearchableSelect
              options={related.map((item) => ({
                value: String(item.id),
                label: optionLabel(item),
              }))}
              value={relationshipFilter}
              onChange={onRelationshipFilterChange}
              className="w-full md:w-96"
              placeholder={`Filtrar por ${relationship.toLowerCase()}`}
              searchPlaceholder={`Buscar ${relationship.toLowerCase()}`}
            />
          ) : null}
          {createAction}
        </>
      }
      secondaryActions={clearAction}
      rows={measurementRows}
    />
  );
}
