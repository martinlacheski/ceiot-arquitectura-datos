import { type FormEvent, useState } from "react";

import { SearchableSelect } from "../../components-searchable-select/SearchableSelect";
import { Button } from "../../components/ui/button";
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "../../components/ui/field";
import { Input } from "../../components/ui/input";
import { Spinner } from "../../components/ui/spinner";
import { showConfirmDialog } from "../../store/confirm.store";
import type { ApiItem, ApiPayload } from "../../shared/api/client";
import type { ResourceDefinition, ResourceField } from "./catalog";
import type { RelatedRecords } from "./useResourceData";

function relatedLabel(
  item: ApiItem,
  relationship: NonNullable<ResourceField["relationship"]>,
) {
  return relationship === "devices"
    ? `${item.name ?? "—"} · ${item.serial_number ?? "—"}`
    : String(item.name ?? item.id);
}

function payloadFor(form: FormData, resource: ResourceDefinition): ApiPayload {
  return resource.fields.reduce<ApiPayload>((payload, field) => {
    const value = String(form.get(field.name) ?? "").trim();
    if (!value) return payload;
    payload[field.name] =
      field.type === "number"
        ? Number(value)
        : field.type === "datetime-local"
          ? new Date(value).toISOString()
          : value;
    return payload;
  }, {});
}

function RelatedField({
  field,
  endpoint,
  related,
  organizationId,
  locationId,
  selectedValue,
  onOrganizationChange,
  onLocationChange,
  onValueChange,
  error,
}: {
  field: ResourceField;
  endpoint: string;
  related: RelatedRecords;
  organizationId: string;
  locationId: string;
  selectedValue: string;
  onOrganizationChange: (value: string) => void;
  onLocationChange: (value: string) => void;
  onValueChange: (value: string) => void;
  error?: string;
}) {
  const isDeviceOrganization =
    endpoint === "devices" && field.name === "organization_id";
  const isDeviceLocation =
    endpoint === "devices" && field.name === "location_id";
  const options = (related[field.relationship!] ?? []).filter(
    (item) =>
      field.relationship !== "locations" ||
      item.organization_id === organizationId,
  );
  const value = isDeviceOrganization
    ? organizationId
    : isDeviceLocation
      ? locationId
      : selectedValue;
  const unavailable =
    options.length === 0 || (isDeviceLocation && !organizationId);
  const placeholder =
    isDeviceLocation && organizationId && options.length === 0
      ? "No hay ubicaciones para esta organización"
      : "Seleccione una opción";
  return (
    <SearchableSelect
      id={`${endpoint}-${field.name}`}
      aria-invalid={Boolean(error)}
      aria-describedby={error ? `${endpoint}-${field.name}-error` : undefined}
      options={options.map((item) => ({
        value: item.id,
        label: relatedLabel(item, field.relationship!),
      }))}
      value={value || undefined}
      onChange={(selected) => {
        const next = selected ?? "";
        if (isDeviceOrganization) onOrganizationChange(next);
        else if (isDeviceLocation) onLocationChange(next);
        else onValueChange(next);
      }}
      placeholder={placeholder}
      emptyMessage="No se encontraron registros relacionados."
      disabled={unavailable}
    />
  );
}

export function ResourceForm({
  resource,
  related,
  submitting,
  onCreate,
  onSuccess,
}: {
  resource: ResourceDefinition;
  related: RelatedRecords;
  submitting: boolean;
  onCreate: (payload: ApiPayload) => Promise<boolean>;
  onSuccess: () => void;
}) {
  const [organizationId, setOrganizationId] = useState("");
  const [locationId, setLocationId] = useState("");
  const [relatedValues, setRelatedValues] = useState<Record<string, string>>(
    {},
  );
  const [relationshipErrors, setRelationshipErrors] = useState<
    Record<string, string>
  >({});

  function relationshipValue(field: ResourceField) {
    if (resource.endpoint === "devices" && field.name === "organization_id") {
      return organizationId;
    }
    if (resource.endpoint === "devices" && field.name === "location_id") {
      return locationId;
    }
    return relatedValues[field.name] ?? "";
  }

  function clearRelationshipError(fieldName: string) {
    setRelationshipErrors((current) => {
      const { [fieldName]: _, ...remaining } = current;
      return remaining;
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const errors = Object.fromEntries(
      resource.fields
        .filter(
          (field) =>
            field.relationship && field.required && !relationshipValue(field),
        )
        .map((field) => [
          field.name,
          `Seleccione una ${field.label.toLowerCase()}.`,
        ]),
    );
    if (Object.keys(errors).length > 0) {
      setRelationshipErrors(errors);
      return;
    }
    const payload = {
      ...payloadFor(new FormData(form), resource),
      ...Object.fromEntries(
        resource.fields
          .filter((field) => field.relationship)
          .map((field) => [field.name, relationshipValue(field)]),
      ),
    };
    showConfirmDialog(resource.createConfirmation, async () => {
      if (!(await onCreate(payload))) {
        throw new Error("No se pudo guardar el registro.");
      }
      form.reset();
      setOrganizationId("");
      setLocationId("");
      setRelatedValues({});
      setRelationshipErrors({});
      onSuccess();
    });
  }

  return (
    <form onSubmit={submit}>
      <FieldGroup>
        {resource.fields.map((field) => (
          <Field
            key={field.name}
            data-invalid={relationshipErrors[field.name] ? true : undefined}
          >
            <FieldLabel htmlFor={`${resource.endpoint}-${field.name}`}>
              {field.label}
              {field.required ? " *" : ""}
            </FieldLabel>
            {field.relationship ? (
              <>
                <RelatedField
                  field={field}
                  endpoint={resource.endpoint}
                  related={related}
                  organizationId={organizationId}
                  locationId={locationId}
                  selectedValue={relatedValues[field.name] ?? ""}
                  onOrganizationChange={(value) => {
                    setOrganizationId(value);
                    setLocationId("");
                    clearRelationshipError(field.name);
                  }}
                  onLocationChange={(value) => {
                    setLocationId(value);
                    clearRelationshipError(field.name);
                  }}
                  onValueChange={(value) => {
                    setRelatedValues((current) => ({
                      ...current,
                      [field.name]: value,
                    }));
                    clearRelationshipError(field.name);
                  }}
                  error={relationshipErrors[field.name]}
                />
                {relationshipErrors[field.name] ? (
                  <FieldError id={`${resource.endpoint}-${field.name}-error`}>
                    {relationshipErrors[field.name]}
                  </FieldError>
                ) : null}
              </>
            ) : (
              <Input
                id={`${resource.endpoint}-${field.name}`}
                name={field.name}
                type={field.type ?? "text"}
                required={field.required}
                step={field.type === "number" ? "any" : undefined}
              />
            )}
          </Field>
        ))}
      </FieldGroup>
      <Button type="submit" className="mt-4 w-full" disabled={submitting}>
        {submitting ? (
          <>
            <Spinner data-icon="inline-start" />
            Guardando…
          </>
        ) : (
          `Crear ${resource.singular}`
        )}
      </Button>
    </form>
  );
}
