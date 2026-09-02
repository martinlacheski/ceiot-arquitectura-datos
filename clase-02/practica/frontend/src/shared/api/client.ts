export type ApiValue = string | number | boolean | null;
export type ApiItem = { id: string; [key: string]: ApiValue };
export type ApiPayload = Record<string, string | number>;

const apiBaseUrl = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/$/, "");

function endpointUrl(endpoint: string): string {
  return `${apiBaseUrl}/${endpoint.replace(/^\//, "")}`;
}

export async function requestList(endpoint: string): Promise<ApiItem[]> {
  const response = await fetch(endpointUrl(endpoint));
  if (!response.ok) throw new Error("No se pudieron cargar los datos.");
  return response.json() as Promise<ApiItem[]>;
}

export async function createItem(
  endpoint: string,
  payload: ApiPayload,
): Promise<ApiItem> {
  const response = await fetch(endpointUrl(endpoint), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok)
    throw new Error(
      "No se pudo guardar. Verifique los identificadores relacionados.",
    );
  return response.json() as Promise<ApiItem>;
}
