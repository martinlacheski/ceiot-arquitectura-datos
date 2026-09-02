export type ResourceEndpoint =
  | "organizations"
  | "locations"
  | "devices"
  | "measurements";

export type ResourceField = {
  name: string;
  label: string;
  type?: "text" | "number" | "datetime-local";
  required?: boolean;
  relationship?: "organizations" | "devices" | "locations";
};

export type ResourceColumn = {
  name: string;
  label: string;
  secondary?: boolean;
  format?: "date";
};

export type MeasurementFilters = {
  organizationId?: string;
  locationId?: string;
  deviceId?: string;
  recordedFrom?: string;
  recordedTo?: string;
};

export type ResourceDefinition = {
  title: string;
  singular: string;
  createLabel: string;
  createConfirmation: string;
  endpoint: ResourceEndpoint;
  description: string;
  fields: ResourceField[];
  columns: ResourceColumn[];
};

export const resources: ResourceDefinition[] = [
  {
    title: "Organizaciones",
    singular: "organización",
    createLabel: "Nueva organización",
    createConfirmation: "¿Desea crear la organización?",
    endpoint: "organizations",
    description: "El contenedor de propiedad del caso de estudio.",
    fields: [{ name: "name", label: "Nombre", required: true }],
    columns: [
      { name: "name", label: "Nombre" },
      { name: "id", label: "ID", secondary: true },
      { name: "created_at", label: "Creada", secondary: true, format: "date" },
    ],
  },
  {
    title: "Ubicaciones",
    singular: "ubicación",
    createLabel: "Nueva ubicación",
    createConfirmation: "¿Desea crear la ubicación?",
    endpoint: "locations",
    description: "Lugares asociados a una organización.",
    fields: [
      {
        name: "organization_id",
        label: "Organización",
        required: true,
        relationship: "organizations",
      },
      { name: "name", label: "Nombre", required: true },
      { name: "description", label: "Descripción" },
      { name: "latitude", label: "Latitud", type: "number" },
      { name: "longitude", label: "Longitud", type: "number" },
    ],
    columns: [
      { name: "name", label: "Nombre" },
      { name: "description", label: "Descripción" },
      { name: "organization_id", label: "Organización", secondary: true },
      { name: "created_at", label: "Creada", secondary: true, format: "date" },
    ],
  },
  {
    title: "Dispositivos",
    singular: "dispositivo",
    createLabel: "Nuevo dispositivo",
    createConfirmation: "¿Desea crear el dispositivo?",
    endpoint: "devices",
    description: "Equipos identificados por su serie dentro del modelo.",
    fields: [
      {
        name: "organization_id",
        label: "Organización",
        required: true,
        relationship: "organizations",
      },
      {
        name: "location_id",
        label: "Ubicación actual",
        required: true,
        relationship: "locations",
      },
      { name: "name", label: "Nombre", required: true },
      { name: "serial_number", label: "Número de serie", required: true },
      { name: "model", label: "Modelo" },
      {
        name: "installed_at",
        label: "Fecha de instalación",
        type: "datetime-local",
      },
    ],
    columns: [
      { name: "name", label: "Nombre" },
      { name: "serial_number", label: "Serie" },
      { name: "model", label: "Modelo" },
      { name: "organization_name", label: "Organización" },
      { name: "current_location_name", label: "Ubicación actual" },
      { name: "created_at", label: "Creado", secondary: true, format: "date" },
    ],
  },
  {
    title: "Mediciones",
    singular: "medición",
    createLabel: "Nueva medición",
    createConfirmation: "¿Desea crear la medición?",
    endpoint: "measurements",
    description: "Observaciones registradas directamente para un dispositivo.",
    fields: [
      {
        name: "device_id",
        label: "Dispositivo",
        required: true,
        relationship: "devices",
      },
      { name: "variable", label: "Variable", required: true },
      { name: "value", label: "Valor", type: "number", required: true },
      { name: "unit", label: "Unidad", required: true },
      {
        name: "recorded_at",
        label: "Fecha y hora",
        type: "datetime-local",
        required: true,
      },
    ],
    columns: [
      { name: "variable", label: "Variable" },
      { name: "value", label: "Valor" },
      { name: "unit", label: "Unidad" },
      { name: "device_id", label: "Dispositivo", secondary: true },
      { name: "recorded_at", label: "Registrada", format: "date" },
    ],
  },
];

export function isResourceEndpoint(
  value: string | null,
): value is ResourceEndpoint {
  return resources.some((resource) => resource.endpoint === value);
}
