import { useCallback, useEffect, useState } from "react";

import {
  createItem,
  requestList,
  type ApiItem,
  type ApiPayload,
} from "../../shared/api/client";
import type { ResourceDefinition } from "./catalog";

type RelatedRecords = Partial<
  Record<"organizations" | "devices" | "locations", ApiItem[]>
>;

function relationshipsFor(resource: ResourceDefinition) {
  return [
    ...new Set(
      resource.fields.flatMap((field) =>
        field.relationship ? [field.relationship] : [],
      ),
    ),
  ];
}

export function useResourceData(resource: ResourceDefinition) {
  const [items, setItems] = useState<ApiItem[]>([]);
  const [related, setRelated] = useState<RelatedRecords>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const relationships = relationshipsFor(resource);
      const [records, ...relatedLists] = await Promise.all([
        requestList(resource.endpoint),
        ...relationships.map((relationship) => requestList(relationship)),
      ]);
      setItems(records);
      setRelated(
        Object.fromEntries(
          relationships.map((relationship, index) => [
            relationship,
            relatedLists[index],
          ]),
        ),
      );
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudieron cargar los datos.",
      );
    } finally {
      setLoading(false);
    }
  }, [resource]);

  useEffect(() => {
    setItems([]);
    setRelated({});
    void load();
  }, [load]);

  const create = useCallback(
    async (payload: ApiPayload) => {
      setError("");
      setSuccess("");
      setSubmitting(true);
      try {
        await createItem(resource.endpoint, payload);
        setSuccess("Registro creado correctamente.");
        await load();
        return true;
      } catch (cause) {
        setError(
          cause instanceof Error
            ? cause.message
            : "No se pudo guardar el registro.",
        );
        return false;
      } finally {
        setSubmitting(false);
      }
    },
    [load, resource.endpoint],
  );

  return { items, related, loading, submitting, error, success, load, create };
}

export type { RelatedRecords };
