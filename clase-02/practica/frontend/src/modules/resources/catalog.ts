export type ResourceField = {
  name: string;
  label: string;
  type?: "text" | "number" | "datetime-local";
  required?: boolean;
};
export type ResourceDefinition = {
  title: string;
  endpoint: string;
  fields: ResourceField[];
};

export const resources: ResourceDefinition[] = [
  {
    title: "Organizaciones",
    endpoint: "organizations",
    fields: [{ name: "name", label: "Nombre", required: true }],
  },
  {
    title: "Ubicaciones",
    endpoint: "locations",
    fields: [
      { name: "organization_id", label: "ID de organización", required: true },
      { name: "name", label: "Nombre", required: true },
      { name: "description", label: "Descripción" },
    ],
  },
  {
    title: "Dispositivos",
    endpoint: "devices",
    fields: [
      { name: "organization_id", label: "ID de organización", required: true },
      { name: "name", label: "Nombre", required: true },
      { name: "serial_number", label: "Número de serie", required: true },
      { name: "model", label: "Modelo" },
    ],
  },
  {
    title: "Mediciones",
    endpoint: "measurements",
    fields: [
      { name: "device_id", label: "ID de dispositivo", required: true },
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
  },
];
