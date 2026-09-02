export type ApiValue = string | number | boolean | null | undefined;
export type ApiItem = { id: string; [key: string]: ApiValue };
export type ApiPayload = Record<string, string | number>;

const apiBaseUrl = (import.meta.env.VITE_API_URL ?? "/api").replace(/\/$/, "");

function endpointUrl(endpoint: string): string {
  return `${apiBaseUrl}/${endpoint.replace(/^\//, "")}`;
}

function healthUrl(): string {
  return apiBaseUrl.endsWith("/api")
    ? `${apiBaseUrl.slice(0, -4)}/health`
    : "/health";
}

async function errorMessage(
  response: Response,
  action: "load" | "create",
): Promise<string> {
  if (response.status === 422)
    return "Revise los campos requeridos y sus formatos.";
  if (response.status === 409)
    return "Ya existe un registro o una relación no es válida.";
  if (response.status >= 500)
    return "La API no pudo completar la operación. Intente nuevamente.";

  try {
    const body = (await response.json()) as { detail?: string };
    if (body.detail) return body.detail;
  } catch {
    // The status still gives the learner a useful next step.
  }
  return action === "load"
    ? "No se pudieron cargar los datos."
    : "No se pudo guardar el registro.";
}

function networkMessage(): string {
  return "No se pudo conectar con la API. Compruebe que los servicios estén en ejecución.";
}

export async function requestList(endpoint: string): Promise<ApiItem[]> {
  let response: Response;
  try {
    response = await fetch(endpointUrl(endpoint));
  } catch {
    throw new Error(networkMessage());
  }
  if (!response.ok) throw new Error(await errorMessage(response, "load"));
  return response.json() as Promise<ApiItem[]>;
}

export async function createItem(
  endpoint: string,
  payload: ApiPayload,
): Promise<ApiItem> {
  let response: Response;
  try {
    response = await fetch(endpointUrl(endpoint), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error(networkMessage());
  }
  if (!response.ok) throw new Error(await errorMessage(response, "create"));
  return response.json() as Promise<ApiItem>;
}

export async function requestHealth(): Promise<boolean> {
  try {
    const response = await fetch(healthUrl());
    return response.ok;
  } catch {
    return false;
  }
}
