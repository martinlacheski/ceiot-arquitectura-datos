import { act, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "../../components/custom/ConfirmDialog";
import { ResourcePanel } from "./ResourcePanel";
import { ResourceTable } from "./ResourceTable";
import {
  applyMeasurementFilter,
  measurementFilterOptions,
  ResourceToolbar,
} from "./ResourceToolbar";
import { resources, type MeasurementFilters } from "./catalog";

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;
class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
Object.assign(globalThis, { ResizeObserver: TestResizeObserver });
Element.prototype.scrollIntoView = () => undefined;

function response(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200 });
}

function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    "value",
  )?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("resource workspace table foundation", () => {
  let container: HTMLDivElement;
  let root: Root;
  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("requires an organization before enabling the device location selector", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const endpoint = url.split("/").pop();
        const data = {
          devices: [],
          organizations: [
            { id: "org-a", name: "Organización A" },
            { id: "org-b", name: "Organización B" },
          ],
          locations: [
            { id: "location-a", name: "Planta A", organization_id: "org-a" },
            { id: "location-b", name: "Planta B", organization_id: "org-b" },
          ],
        };
        return Promise.resolve(response(data[endpoint as keyof typeof data]));
      }),
    );
    const deviceResource = resources.find(
      ({ endpoint }) => endpoint === "devices",
    )!;
    await act(async () =>
      root.render(<ResourcePanel resource={deviceResource} />),
    );
    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Nuevo dispositivo"),
    );
    expect(newButton).toBeDefined();
    await act(async () => newButton?.click());
    expect(
      document.querySelector('[data-slot="dialog-title"]')?.textContent,
    ).toContain("Nuevo dispositivo");
    const selectors =
      document.querySelectorAll<HTMLButtonElement>('[role="combobox"]');
    const location = selectors[2];
    expect(location.disabled).toBe(true);
    expect(
      document.querySelector<HTMLInputElement>("#devices-organization_id")
        ?.value,
    ).toBe("");
    expect(location.textContent).toContain("Seleccione una opción");
  });

  it("closes and resets the creation dialog after a successful submission", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init?: RequestInit) =>
        Promise.resolve(
          response(
            init?.method === "POST"
              ? { id: "org-a", name: "Organización A" }
              : [{ id: "org-a", name: "Organización A" }],
          ),
        ),
      ),
    );
    const organizationResource = resources.find(
      ({ endpoint }) => endpoint === "organizations",
    )!;
    await act(async () =>
      root.render(
        <>
          <ResourcePanel resource={organizationResource} />
          <ConfirmDialog />
        </>,
      ),
    );
    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "Nueva organización",
    )!;
    await act(async () => newButton.click());
    const name = document.querySelector<HTMLInputElement>(
      "#organizations-name",
    )!;
    name.value = "Organización A";
    await act(async () => name.form?.requestSubmit());
    const confirm = Array.from(document.querySelectorAll("button")).find(
      (button) => button.textContent === "Sí",
    )!;
    await act(async () => confirm.click());
    expect(document.querySelector('[data-slot="dialog-content"]')).toBeNull();
    await act(async () => newButton.click());
    expect(
      document.querySelector<HTMLInputElement>("#organizations-name")?.value,
    ).toBe("");
  });

  it("blocks confirmation and POST when a required relationship is missing", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      const endpoint = url.split("/").pop();
      if (init?.method === "POST") {
        return Promise.resolve(response({ id: "location-a" }));
      }
      return Promise.resolve(
        response(
          endpoint === "organizations"
            ? [{ id: "org-a", name: "Organización A" }]
            : [],
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    const locationResource = resources.find(
      ({ endpoint }) => endpoint === "locations",
    )!;
    await act(async () =>
      root.render(
        <>
          <ResourcePanel resource={locationResource} />
          <ConfirmDialog />
        </>,
      ),
    );
    const newButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "Nueva ubicación",
    )!;
    await act(async () => newButton.click());
    const name = document.querySelector<HTMLInputElement>("#locations-name")!;
    name.value = "Planta A";
    await act(async () => name.form?.requestSubmit());

    const relationship = document
      .querySelector<HTMLButtonElement>("#locations-organization_id")!
      .closest('[data-slot="field"]')!;
    expect(relationship.getAttribute("data-invalid")).toBe("true");
    expect(
      relationship
        .querySelector('[role="combobox"]')
        ?.getAttribute("aria-invalid"),
    ).toBe("true");
    expect(relationship.querySelector('[role="alert"]')?.textContent).toContain(
      "Seleccione una organización.",
    );
    expect(
      document.querySelector('[data-slot="alert-dialog-content"]'),
    ).toBeNull();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/locations",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("filters location rows by their organization relationship", async () => {
    const resource = resources.find(
      ({ endpoint }) => endpoint === "locations",
    )!;
    await act(async () =>
      root.render(
        <ResourceTable
          resource={resource}
          search=""
          relationshipFilter="org-a"
          items={[
            { id: "location-a", name: "Planta A", organization_id: "org-a" },
            { id: "location-b", name: "Planta B", organization_id: "org-b" },
          ]}
        />,
      ),
    );
    expect(container.querySelector("table")?.textContent).toContain("Planta A");
    expect(container.querySelector("table")?.textContent).not.toContain(
      "Planta B",
    );
  });

  it("renders the complete measurement toolbar in its required DOM order", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const endpoint = url.split("/").pop();
        const data = {
          measurements: [],
          devices: [
            {
              id: "device-a",
              name: "Termómetro A",
              organization_id: "org-a",
              organization_name: "Organización A",
              current_location_id: "location-a",
              current_location_name: "Planta A",
            },
            {
              id: "device-b",
              name: "Termómetro B",
              organization_id: "org-b",
              organization_name: "Organización B",
              current_location_id: "location-b",
              current_location_name: "Planta B",
            },
          ],
        };
        return Promise.resolve(
          response(data[endpoint as keyof typeof data] ?? []),
        );
      }),
    );
    const measurementResource = resources.find(
      ({ endpoint }) => endpoint === "measurements",
    )!;
    await act(async () =>
      root.render(<ResourcePanel resource={measurementResource} />),
    );

    const toolbar = container.querySelector('[data-testid="list-toolbar"]')!;
    const rowOne = toolbar.querySelector('[data-testid="list-toolbar-row-1"]')!;
    const rowTwo = toolbar.querySelector('[data-testid="list-toolbar-row-2"]')!;
    expect(
      Array.from(rowOne.querySelectorAll("input, button")).map((control) =>
        control instanceof HTMLInputElement
          ? "search"
          : control.textContent?.trim(),
      ),
    ).toEqual([
      "search",
      "Filtrar por organización",
      "Seleccione primero una organización",
      "Seleccione primero una ubicación",
    ]);
    expect(
      Array.from(rowTwo.querySelectorAll("input, button")).map((control) => {
        if (control instanceof HTMLInputElement) {
          return control.id === "measurements-recorded-from"
            ? "date-from"
            : "date-to";
        }
        return control.textContent?.trim();
      }),
    ).toEqual(["date-from", "date-to", "Nueva medición", "Limpiar filtros"]);

    const selectors =
      toolbar.querySelectorAll<HTMLButtonElement>('[role="combobox"]');

    expect(selectors[1].disabled).toBe(true);
    expect(selectors[2].disabled).toBe(true);
  });

  it("keeps the standard toolbar layout for non-measurement resources", async () => {
    const organizationResource = resources.find(
      ({ endpoint }) => endpoint === "organizations",
    )!;
    await act(async () =>
      root.render(
        <ResourceToolbar
          resource={organizationResource}
          related={[]}
          search=""
          onSearchChange={() => undefined}
          onRelationshipFilterChange={() => undefined}
          onCreate={() => undefined}
        />,
      ),
    );

    const toolbar = container.querySelector('[data-testid="list-toolbar"]')!;
    expect(
      toolbar.querySelector('[data-testid="list-toolbar-row-1"]'),
    ).toBeNull();
    expect(
      toolbar.querySelector('[data-testid="list-toolbar-row-2"]'),
    ).toBeNull();
    expect(
      toolbar.querySelector('[data-testid="list-toolbar-search"]'),
    ).not.toBeNull();
    expect(
      toolbar.querySelector('[data-testid="list-toolbar-actions"]'),
    ).not.toBeNull();
  });

  it("cascades measurement selections and scopes their options", () => {
    const devices = [
      {
        id: "device-a",
        name: "Termómetro A",
        organization_id: "org-a",
        organization_name: "Organización A",
        current_location_id: "location-a",
        current_location_name: "Planta A",
      },
      {
        id: "device-b",
        name: "Termómetro B",
        organization_id: "org-b",
        organization_name: "Organización B",
        current_location_id: "location-b",
        current_location_name: "Planta B",
      },
    ];
    const selectedOrganization = applyMeasurementFilter(
      { locationId: "stale-location", deviceId: "stale-device" },
      "organizationId",
      "org-a",
    );
    expect(selectedOrganization).toEqual({ organizationId: "org-a" });
    expect(
      measurementFilterOptions(devices, selectedOrganization).locations,
    ).toEqual([{ value: "location-a", label: "Planta A" }]);

    const selectedLocation = applyMeasurementFilter(
      { ...selectedOrganization, deviceId: "stale-device" },
      "locationId",
      "location-a",
    );
    expect(selectedLocation).toEqual({
      organizationId: "org-a",
      locationId: "location-a",
    });
    expect(
      measurementFilterOptions(devices, selectedLocation).filteredDevices.map(
        (device) => device.id,
      ),
    ).toEqual(["device-a"]);
    expect(
      applyMeasurementFilter(selectedLocation, "organizationId", undefined),
    ).toEqual({});
  });

  it("provides client-side search and pagination controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const endpoint = url.split("/").pop();
        const organizations = Array.from({ length: 12 }, (_, index) => ({
          id: `org-${index + 1}`,
          name:
            index === 0 ? "Laboratorio central" : `Organización ${index + 1}`,
        }));
        return Promise.resolve(
          response(
            { organizations, devices: [], locations: [] }[
              endpoint as "organizations" | "devices" | "locations"
            ],
          ),
        );
      }),
    );
    const resource = resources.find(
      ({ endpoint }) => endpoint === "organizations",
    )!;
    await act(async () => root.render(<ResourcePanel resource={resource} />));
    expect(container.textContent).toContain("Mostrar");
    expect(container.textContent).toContain("Página 1 de 2");
    expect(container.querySelector("table")?.textContent).not.toContain(
      "Organización 12",
    );
    const search = container.querySelector<HTMLInputElement>(
      "[data-list-toolbar-search-control]",
    )!;
    await act(async () => {
      search.value = "central";
      search.dispatchEvent(new Event("change", { bubbles: true }));
      search.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.querySelector("table")?.textContent).toContain(
      "Laboratorio central",
    );
    expect(container.querySelector("table")?.textContent).not.toContain(
      "Organización 2",
    );
  });

  it("intersects measurement relationships and inclusive calendar dates", async () => {
    const measurementResource = resources.find(
      ({ endpoint }) => endpoint === "measurements",
    )!;
    await act(async () =>
      root.render(
        <ResourceTable
          resource={measurementResource}
          search="temperature"
          measurementFilters={{
            organizationId: "org-a",
            locationId: "location-a",
            deviceId: "device-a",
            recordedFrom: "2025-01-10",
            recordedTo: "2025-01-10",
          }}
          devices={[
            {
              id: "device-a",
              name: "Termómetro A",
              organization_id: "org-a",
              current_location_id: "location-a",
            },
            {
              id: "device-b",
              name: "Termómetro B",
              organization_id: "org-a",
              current_location_id: "location-b",
            },
          ]}
          items={[
            {
              id: "measurement-a",
              device_id: "device-a",
              variable: "temperature",
              value: 22,
              unit: "°C",
              recorded_at: "2025-01-10T23:59:00-03:00",
            },
            {
              id: "measurement-b",
              device_id: "device-a",
              variable: "humidity",
              value: 60,
              unit: "%",
              recorded_at: "2025-01-10T00:00:00-03:00",
            },
            {
              id: "measurement-c",
              device_id: "device-b",
              variable: "temperature",
              value: 21,
              unit: "°C",
              recorded_at: "2025-01-10T12:00:00-03:00",
            },
          ]}
        />,
      ),
    );
    expect(container.querySelector("table")?.textContent).toContain("22");
    expect(container.querySelector("table")?.textContent).not.toContain("60");
    expect(container.querySelector("table")?.textContent).not.toContain("21");

    await act(async () =>
      root.render(
        <ResourceTable
          resource={measurementResource}
          search=""
          measurementFilters={{
            recordedFrom: "2025-01-11",
            recordedTo: "2025-01-10",
          }}
          devices={[]}
          items={[
            {
              id: "measurement-a",
              device_id: "device-a",
              variable: "temperature",
              value: 22,
              unit: "°C",
              recorded_at: "2025-01-10T23:59:00-03:00",
            },
          ]}
        />,
      ),
    );
    expect(container.textContent).toContain("No hay resultados");
  });

  it("resets pagination when the measurement filter changes", async () => {
    const measurementResource = resources.find(
      ({ endpoint }) => endpoint === "measurements",
    )!;
    const devices = [
      {
        id: "device-a",
        name: "Termómetro A",
        organization_id: "org-a",
        current_location_id: "location-a",
      },
    ];
    const items = Array.from({ length: 12 }, (_, index) => ({
      id: `measurement-${index}`,
      device_id: "device-a",
      variable: "temperature",
      value: index,
      unit: "°C",
      recorded_at: "2025-01-10T12:00:00-03:00",
    }));
    await act(async () =>
      root.render(
        <ResourceTable
          resource={measurementResource}
          search=""
          measurementFilters={{}}
          devices={devices}
          items={items}
        />,
      ),
    );
    const next = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Ir a la página siguiente"),
    )!;
    await act(async () => next.click());
    expect(container.textContent).toContain("Página 2 de 2");

    await act(async () =>
      root.render(
        <ResourceTable
          resource={measurementResource}
          search="temperature"
          measurementFilters={{}}
          devices={devices}
          items={items}
        />,
      ),
    );
    expect(container.textContent).toContain("Página 1 de 2");

    const nextAfterSearch = Array.from(
      container.querySelectorAll("button"),
    ).find((button) =>
      button.textContent?.includes("Ir a la página siguiente"),
    )!;
    await act(async () => nextAfterSearch.click());
    expect(container.textContent).toContain("Página 2 de 2");

    await act(async () =>
      root.render(
        <ResourceTable
          resource={measurementResource}
          search="temperature"
          measurementFilters={{ recordedFrom: "2025-01-10" }}
          devices={devices}
          items={items}
        />,
      ),
    );
    expect(container.textContent).toContain("Página 1 de 2");
  });

  it("clears all measurement filters without another API request and restores the full first page", async () => {
    const measurementResource = resources.find(
      ({ endpoint }) => endpoint === "measurements",
    )!;
    const devices = [
      {
        id: "device-a",
        name: "Termómetro A",
        organization_id: "org-a",
        organization_name: "Organización A",
        current_location_id: "location-a",
        current_location_name: "Planta A",
      },
      {
        id: "device-b",
        name: "Termómetro B",
        organization_id: "org-b",
        organization_name: "Organización B",
        current_location_id: "location-b",
        current_location_name: "Planta B",
      },
    ];
    const measurements = Array.from({ length: 12 }, (_, index) => ({
      id: `measurement-${index}`,
      device_id: index === 0 ? "device-a" : "device-b",
      variable: index === 0 ? "temperature target" : "humidity",
      value: index,
      unit: "%",
      recorded_at:
        index === 0 ? "2025-01-10T12:00:00-03:00" : "2025-01-11T12:00:00-03:00",
    }));
    const fetchMock = vi.fn((url: string) => {
      const endpoint = url.split("/").pop();
      return Promise.resolve(
        response(
          { measurements, devices }[endpoint as "measurements" | "devices"] ??
            [],
        ),
      );
    });
    vi.stubGlobal("fetch", fetchMock);
    await act(async () =>
      root.render(<ResourcePanel resource={measurementResource} />),
    );

    const toolbar = container.querySelector('[data-testid="list-toolbar"]')!;
    const search = toolbar.querySelector<HTMLInputElement>(
      "[data-list-toolbar-search-control]",
    )!;
    const from = toolbar.querySelector<HTMLInputElement>(
      "#measurements-recorded-from",
    )!;
    const to = toolbar.querySelector<HTMLInputElement>(
      "#measurements-recorded-to",
    )!;
    await act(async () => {
      setInputValue(search, "target");
      setInputValue(from, "2025-01-10");
      setInputValue(to, "2025-01-10");
    });
    expect(container.querySelector("table")?.textContent).toContain("target");

    const callsAfterInitialLoads = fetchMock.mock.calls.length;
    const clear = Array.from(toolbar.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Limpiar filtros"),
    )!;
    await act(async () => clear.click());

    expect(search.value).toBe("");
    expect(from.value).toBe("");
    expect(to.value).toBe("");
    expect(container.textContent).toContain("Página 1 de 2");
    expect(container.querySelectorAll("tbody tr")).toHaveLength(10);
    expect(fetchMock).toHaveBeenCalledTimes(callsAfterInitialLoads);
  });

  it("clears selected measurement relationships from the rendered toolbar", async () => {
    const measurementResource = resources.find(
      ({ endpoint }) => endpoint === "measurements",
    )!;
    const related = [
      {
        id: "device-a",
        name: "Termómetro A",
        organization_id: "org-a",
        organization_name: "Organización A",
        current_location_id: "location-a",
        current_location_name: "Planta A",
      },
    ];
    function ToolbarHarness() {
      const [search, setSearch] = useState("target");
      const [filters, setFilters] = useState<MeasurementFilters>({
        organizationId: "org-a",
        locationId: "location-a",
        deviceId: "device-a",
        recordedFrom: "2025-01-10",
        recordedTo: "2025-01-10",
      });
      return (
        <ResourceToolbar
          resource={measurementResource}
          related={related}
          search={search}
          onSearchChange={setSearch}
          onRelationshipFilterChange={() => undefined}
          measurementFilters={filters}
          onMeasurementFiltersChange={setFilters}
          onCreate={() => undefined}
        />
      );
    }
    await act(async () => root.render(<ToolbarHarness />));
    const toolbar = container.querySelector('[data-testid="list-toolbar"]')!;
    expect(toolbar.textContent).toContain("Organización A");
    expect(toolbar.textContent).toContain("Planta A");
    expect(toolbar.textContent).toContain("Termómetro A");

    const clear = Array.from(toolbar.querySelectorAll("button")).find(
      (button) => button.textContent?.includes("Limpiar filtros"),
    )!;
    await act(async () => clear.click());

    expect(
      toolbar.querySelector<HTMLInputElement>(
        "[data-list-toolbar-search-control]",
      )?.value,
    ).toBe("");
    expect(
      toolbar.querySelector<HTMLInputElement>("#measurements-recorded-from")
        ?.value,
    ).toBe("");
    expect(
      toolbar.querySelector<HTMLInputElement>("#measurements-recorded-to")
        ?.value,
    ).toBe("");
    const selectors =
      toolbar.querySelectorAll<HTMLButtonElement>('[role="combobox"]');
    expect(selectors[0].textContent).toContain("Filtrar por organización");
    expect(selectors[1].textContent).toContain(
      "Seleccione primero una organización",
    );
    expect(selectors[2].textContent).toContain(
      "Seleccione primero una ubicación",
    );
  });

  it("marks an invalid measurement date range accessibly and hides rows", async () => {
    const measurementResource = resources.find(
      ({ endpoint }) => endpoint === "measurements",
    )!;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        const endpoint = url.split("/").pop();
        return Promise.resolve(
          response(
            endpoint === "measurements"
              ? [
                  {
                    id: "measurement-a",
                    device_id: "device-a",
                    variable: "temperature",
                    value: 22,
                    unit: "°C",
                    recorded_at: "2025-01-10T12:00:00-03:00",
                  },
                ]
              : [],
          ),
        );
      }),
    );
    await act(async () =>
      root.render(<ResourcePanel resource={measurementResource} />),
    );
    const from = container.querySelector<HTMLInputElement>(
      "#measurements-recorded-from",
    )!;
    const to = container.querySelector<HTMLInputElement>(
      "#measurements-recorded-to",
    )!;
    await act(async () => {
      setInputValue(from, "2025-01-11");
      setInputValue(to, "2025-01-10");
    });

    expect(from.getAttribute("aria-invalid")).toBe("true");
    expect(to.getAttribute("aria-invalid")).toBe("true");
    expect(
      container.querySelector('[data-slot="field"][data-invalid="true"]'),
    ).not.toBeNull();
    expect(container.querySelector('[role="alert"]')?.textContent).toContain(
      "La fecha desde no puede ser posterior a la fecha hasta.",
    );
    expect(container.querySelector("table")).toBeNull();
    expect(container.textContent).toContain("No hay resultados");
  });
});
