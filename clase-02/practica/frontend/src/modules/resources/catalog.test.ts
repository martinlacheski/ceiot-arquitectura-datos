import { afterEach, describe, expect, it, vi } from "vitest";

import { createItem, requestList } from "../../shared/api/client";
import { resources } from "./catalog";

describe("resource catalog", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("expone los cuatro flujos de alta y listado de la práctica", () => {
    expect(resources.map((resource) => resource.endpoint)).toEqual([
      "organizations",
      "locations",
      "devices",
      "measurements",
    ]);
    expect(
      resources
        .flatMap((resource) => resource.fields)
        .filter((field) => field.required),
    ).not.toHaveLength(0);
    expect(
      resources
        .find((resource) => resource.endpoint === "locations")
        ?.fields.find((field) => field.name === "description")?.required,
    ).toBeUndefined();
  });

  it("lista recursos desde la API local", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify([{ id: "org-1", name: "Laboratorio" }]), {
          status: 200,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestList("organizations")).resolves.toEqual([
      { id: "org-1", name: "Laboratorio" },
    ]);
    expect(fetchMock).toHaveBeenCalledWith("/api/organizations");
  });

  it("crea recursos con JSON y reporta errores HTTP", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "org-1", name: "Laboratorio" }), {
          status: 201,
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 409 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      createItem("organizations", { name: "Laboratorio" }),
    ).resolves.toEqual({ id: "org-1", name: "Laboratorio" });
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/organizations",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Laboratorio" }),
      }),
    );
    await expect(
      createItem("organizations", { name: "Duplicada" }),
    ).rejects.toThrow("No se pudo guardar");
  });
});
