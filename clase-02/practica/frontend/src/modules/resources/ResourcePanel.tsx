import { type FormEvent, useEffect, useState } from "react";

import {
  createItem,
  requestList,
  type ApiItem,
  type ApiPayload,
} from "../../shared/api/client";
import type { ResourceDefinition } from "./catalog";

function summarize(item: ApiItem): string {
  return Object.entries(item)
    .filter(([key]) => key !== "id" && key !== "created_at")
    .slice(0, 4)
    .map(([key, value]) => `${key}: ${String(value ?? "—")}`)
    .join(" · ");
}

export function ResourcePanel({ resource }: { resource: ResourceDefinition }) {
  const [items, setItems] = useState<ApiItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      setItems(await requestList(resource.endpoint));
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudieron cargar los datos.",
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [resource.endpoint]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setError("");
    setSuccess("");
    const form = new FormData(formElement);
    const payload = Object.fromEntries(form.entries()) as ApiPayload;
    if (resource.endpoint === "measurements") {
      payload.recorded_at = new Date(String(payload.recorded_at)).toISOString();
      payload.value = Number(payload.value);
    }
    try {
      await createItem(resource.endpoint, payload);
      formElement.reset();
      setSuccess("Registro creado correctamente.");
      await load();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo guardar el registro.",
      );
    }
  }

  return (
    <article
      className="resource-panel"
      aria-labelledby={`${resource.endpoint}-title`}
    >
      <h2 id={`${resource.endpoint}-title`}>{resource.title}</h2>
      <form className="resource-form" onSubmit={submit}>
        {resource.fields.map((field) => (
          <label
            key={field.name}
            htmlFor={`${resource.endpoint}-${field.name}`}
          >
            {field.label}
            <input
              id={`${resource.endpoint}-${field.name}`}
              name={field.name}
              type={field.type ?? "text"}
              required={field.required ?? false}
            />
          </label>
        ))}
        <button type="submit">
          Crear {resource.title.slice(0, -2).toLowerCase()}
        </button>
      </form>
      {success && (
        <p className="success-message" role="status">
          {success}
        </p>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <p aria-live="polite">Cargando registros…</p>
      ) : items.length === 0 ? (
        <p>No hay registros todavía.</p>
      ) : (
        <ul
          className="resource-list"
          aria-label={`Registros de ${resource.title.toLowerCase()}`}
        >
          {items.map((item) => (
            <li key={item.id}>{summarize(item)}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
