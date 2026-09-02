# Clase 2: modelado de datos

Esta clase continúa el caso IoT de la Clase 1: transforma requerimientos en un modelo conceptual, lógico y físico que puede inspeccionarse y ejecutarse.

## Ruta rápida

1. Lea los [requerimientos](practica/docs/requirements.md).
2. Compare el modelo [conceptual](practica/docs/modeling/conceptual.svg), el modelo [lógico](practica/docs/modeling/logical.svg) y el modelo [físico](practica/docs/modeling/physical.sql).
3. Siga la práctica ejecutable en [`practica/README.md`](practica/README.md).

## Accesos rápidos

Después de ejecutar `docker compose up --build` desde `clase-02/practica`:

- [Frontend — aplicación IoT](http://localhost:5173)
- [Backend — estado de la API](http://localhost:8000/health)
- [Backend — documentación interactiva](http://localhost:8000/api/docs)
- [Backend — organizaciones](http://localhost:8000/api/organizations)

Estos enlaces utilizan los valores predeterminados de `.env.example`. Si cambia `BACKEND_HOST_PORT` o `FRONTEND_HOST_PORT`, ajuste las URLs según corresponda.

> `organization_id` organiza propiedad y alcance del caso. En esta clase **no** implementa autenticación, autorización, `TenantContext` ni Row Level Security.
