import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { resources } from "../modules/resources/catalog";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const apiRows = {
  organizations: [
    {
      id: "org-1",
      name: "Laboratorio central",
      created_at: "2025-01-01T00:00:00Z",
    },
  ],
  locations: [],
  devices: [
    {
      id: "device-1",
      name: "Termómetro norte",
      serial_number: "TN-01",
      created_at: "2025-01-01T00:00:00Z",
    },
  ],
  measurements: [],
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

describe("Clase 2 resource workspace", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    window.history.replaceState({}, "", "/");
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        if (options?.method === "POST") {
          return Promise.resolve(
            response({ id: "org-2", name: "Nueva organización" }, 201),
          );
        }
        const endpoint = url.split("/").pop() as keyof typeof apiRows;
        return Promise.resolve(response(apiRows[endpoint]));
      }),
    );
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  async function renderApp() {
    await act(async () => root.render(<App />));
  }

  it("mantiene un único recurso activo, enfoca la pestaña y sincroniza la URL", async () => {
    await renderApp();

    expect(container.querySelectorAll('[role="tabpanel"]')).toHaveLength(1);
    expect(container.textContent).toContain("Laboratorio central");
    expect(container.textContent).not.toContain("Termómetro norte");

    const devicesTab =
      container.querySelector<HTMLButtonElement>("#tab-devices");
    expect(devicesTab).not.toBeNull();
    await act(async () => devicesTab?.click());

    expect(window.location.search).toBe("?resource=devices");
    expect(document.activeElement).toBe(devicesTab);
    expect(container.querySelectorAll('[role="tabpanel"]')).toHaveLength(1);
    expect(container.querySelector("table")?.textContent).toContain(
      "Termómetro norte",
    );
    expect(container.querySelector("table")?.textContent).not.toContain(
      "Laboratorio central",
    );
  });

  it("recupera la pestaña elegida desde la URL y ofrece selectores de entidades relacionadas", async () => {
    window.history.replaceState({}, "", "?resource=devices");
    await renderApp();

    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Nuevo dispositivo"),
    );
    expect(newButton).toBeDefined();
    await act(async () => newButton?.click());

    expect(document.querySelector("#devices-organization_id")).toBeInstanceOf(
      HTMLButtonElement,
    );
    expect(document.querySelectorAll('[role="combobox"]')).toHaveLength(4);
  });

  it("explica el estado vacío y ofrece el alta mediante un modal", async () => {
    window.history.replaceState({}, "", "?resource=locations");
    await renderApp();

    expect(container.textContent).toContain("Aún no hay ubicaciones");
    expect(container.querySelector("form")).toBeNull();
    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "Nueva ubicación",
    );
    expect(newButton).toBeDefined();
    await act(async () => newButton?.click());
    expect(
      document.querySelector('[data-slot="dialog-title"]')?.textContent,
    ).toContain("Nueva ubicación");
    expect(document.querySelector("#locations-organization_id")).toBeInstanceOf(
      HTMLButtonElement,
    );
  });

  it("muestra el botón de creación exacto en cada pestaña", async () => {
    await renderApp();
    for (const resource of resources) {
      const tab = container.querySelector<HTMLButtonElement>(
        `#tab-${resource.endpoint}`,
      )!;
      await act(async () => tab.click());
      expect(
        Array.from(container.querySelectorAll("button")).some(
          (button) => button.textContent === resource.createLabel,
        ),
      ).toBe(true);
    }
  });

  it("ubica cada filtro de relación antes de crear y usa Limpiar filtros", async () => {
    await renderApp();
    for (const endpoint of ["locations", "devices", "measurements"] as const) {
      const tab = container.querySelector<HTMLButtonElement>(
        `#tab-${endpoint}`,
      )!;
      await act(async () => tab.click());
      const toolbar = container.querySelector('[data-testid="list-toolbar"]')!;
      const search = toolbar.querySelector(
        '[data-testid="list-toolbar-search"]',
      )!;
      const controls = Array.from(toolbar.querySelectorAll("button"));
      const filter = controls.find(
        (control) => control.getAttribute("role") === "combobox",
      );
      const create = controls.find(
        (control) =>
          control.textContent ===
          resources.find((resource) => resource.endpoint === endpoint)
            ?.createLabel,
      );

      expect(filter).toBeDefined();
      expect(create).toBeDefined();
      expect(
        search.compareDocumentPosition(filter!) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
      expect(
        filter!.compareDocumentPosition(create!) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    }
    expect(container.textContent).toContain("Limpiar filtros");
    expect(container.textContent).not.toContain("Limpiar búsqueda");
  });

  it("solicita confirmación antes de crear y solo publica después de Sí", async () => {
    await renderApp();

    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "Nueva organización",
    );
    await act(async () => newButton?.click());
    const name = document.querySelector<HTMLInputElement>(
      "#organizations-name",
    )!;
    name.value = "Nueva organización";
    await act(async () => name.form?.requestSubmit());

    expect(fetch).not.toHaveBeenCalledWith(
      "/api/organizations",
      expect.objectContaining({ method: "POST" }),
    );
    expect(document.body.textContent).toContain(
      "¿Desea crear la organización?",
    );

    const cancel = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent === "No",
    );
    await act(async () => cancel?.click());
    expect(fetch).not.toHaveBeenCalledWith(
      "/api/organizations",
      expect.objectContaining({ method: "POST" }),
    );

    await act(async () => name.form?.requestSubmit());
    const confirm = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent === "Sí",
    );
    await act(async () => confirm?.click());

    expect(fetch).toHaveBeenCalledWith(
      "/api/organizations",
      expect.objectContaining({ method: "POST" }),
    );
    expect(document.querySelector('[data-slot="dialog-content"]')).toBeNull();
    expect(
      document.querySelector('[data-slot="alert-dialog-content"]'),
    ).toBeNull();
    expect(
      document.querySelector<HTMLInputElement>("#organizations-name"),
    ).toBeNull();
  });

  it("mantiene el alta abierta y permite recuperarse de un POST fallido", async () => {
    let resolvePost: ((value: Response) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, options?: RequestInit) => {
        if (options?.method === "POST") {
          return new Promise<Response>((resolve) => {
            resolvePost = resolve;
          });
        }
        const endpoint = url.split("/").pop() as keyof typeof apiRows;
        return Promise.resolve(response(apiRows[endpoint]));
      }),
    );
    await renderApp();
    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "Nueva organización",
    )!;
    await act(async () => newButton.click());
    const name = document.querySelector<HTMLInputElement>(
      "#organizations-name",
    )!;
    name.value = "Nueva organización";
    await act(async () => name.form?.requestSubmit());
    const confirm = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent === "Sí",
    )!;
    await act(async () => confirm.click());

    const pendingActions = Array.from(
      document.querySelectorAll("button"),
    ).filter(
      (button) =>
        button.textContent === "Procesando…" || button.textContent === "No",
    );
    expect(pendingActions.every((button) => button.disabled)).toBe(true);
    expect(
      document.querySelector('[data-slot="dialog-content"]'),
    ).not.toBeNull();

    await act(async () =>
      resolvePost?.(response({ detail: "No permitido" }, 409)),
    );
    expect(
      document.querySelector('[data-slot="alert-dialog-content"]'),
    ).not.toBeNull();
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(
      "Ya existe un registro o una relación no es válida.",
    );
    const cancel = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent === "No",
    )!;
    await act(async () => cancel.click());
    expect(
      document.querySelector('[data-slot="alert-dialog-content"]'),
    ).toBeNull();
    expect(
      document.querySelector('[data-slot="dialog-content"]'),
    ).not.toBeNull();
  });

  it("muestra un error recuperable cuando la API no responde", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
    );
    await renderApp();

    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      "No se pudo conectar con la API",
    );
    expect(
      container.querySelector<HTMLButtonElement>("#retry-resource"),
    ).not.toBeNull();
  });
});
