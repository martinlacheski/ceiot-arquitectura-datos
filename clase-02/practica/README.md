# Práctica: del requerimiento al modelo IoT ejecutable

Esta práctica conecta tres vistas del mismo caso: requisitos y diagramas, DDL PostgreSQL y una API/UI mínima para crear y listar organizaciones, ubicaciones, dispositivos y mediciones.

## Camino rápido

1. Copie `.env.example` como `.env` y ajuste los valores locales si fuera necesario.
2. Ejecute `docker compose up --build` desde este directorio.
3. Abra `http://FRONTEND_PUBLIC_HOST:FRONTEND_HOST_PORT`, cree una organización y reutilice su ID al crear ubicaciones y dispositivos.
4. Consulte `http://BACKEND_PUBLIC_HOST:BACKEND_HOST_PORT/api/docs` para inspeccionar la API y `http://BACKEND_PUBLIC_HOST:BACKEND_HOST_PORT/health` para comprobar la disponibilidad.

Con los valores predeterminados, las direcciones son `http://localhost:5173`, `http://localhost:8000/api/docs` y `http://localhost:8000/health`.

> La práctica no implementa login, autorización, RLS ni `TenantContext`. `organization_id` representa propiedad del dominio y permite relacionar ejemplos; no es una frontera de seguridad.

## API y rutas

Los recursos de la API usan el prefijo `/api`: por ejemplo, `GET /api/organizations` y `POST /api/measurements`. La comprobación de disponibilidad canónica no lleva prefijo: `GET /health`. El navegador llama a `/api` y Vite conserva esa ruta al reenviarla hacia `BACKEND_HOST_URL`. Dentro de Compose, esa URL se resuelve como `http://backend:8000`; no debe incluir `/api`, porque la solicitud ya contiene ese prefijo.

## Mapa de la práctica

| Área | Punto de entrada | Qué muestra |
| --- | --- | --- |
| Requerimientos | [`docs/requirements.md`](docs/requirements.md) | Reglas de negocio y límites deliberados |
| Modelo conceptual | [Vista SVG](docs/modeling/conceptual.svg) · [Fuente Mermaid](docs/modeling/conceptual.mmd) | Entidades y relaciones |
| Modelo lógico | [Vista SVG](docs/modeling/logical.svg) · [Fuente Mermaid](docs/modeling/logical.mmd) | Claves, atributos y cardinalidades |
| Modelo físico | [`docs/modeling/physical.sql`](docs/modeling/physical.sql) | DDL ejecutable con tablas, constraints e índices PostgreSQL |
| API | [`backend/app/main.py`](backend/app/main.py) | Capas router → service → repository → SQLModel |
| UI | [`frontend/src/core/App.tsx`](frontend/src/core/App.tsx) | Flujos accesibles de listado y creación |

## Ejecución local

### Con Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

PostgreSQL inicializa el esquema con `docs/modeling/physical.sql` y después carga los datos de muestra desde `database/sql/02-seed.sql`. Los pares `POSTGRES_BIND_HOST`/`POSTGRES_HOST_PORT`, `BACKEND_BIND_HOST`/`BACKEND_HOST_PORT` y `FRONTEND_BIND_HOST`/`FRONTEND_HOST_PORT` controlan las interfaces y puertos publicados. `BACKEND_PUBLIC_HOST` y `FRONTEND_PUBLIC_HOST` se usan para las URLs que abre el navegador. Dentro de la red de contenedores, los servicios conservan sus nombres y puertos internos (`postgres:5432`, `backend:8000` y `frontend:5173`).

### Comprobar la instalación

En una instalación limpia, `docker compose up --build` crea el volumen de PostgreSQL, ejecuta primero `docs/modeling/physical.sql` y después carga `database/sql/02-seed.sql`.

Comprobar que el backend utiliza la base creada:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/organizations
```

La primera respuesta debe informar `{"status":"ok","database":"connected"}` y la segunda debe devolver las organizaciones cargadas por el archivo de datos de muestra.

### Reiniciar la práctica si ya existía un volumen

Este paso no es necesario durante la primera instalación. Utilícelo solamente cuando necesite descartar una base anterior y volver a ejecutar `physical.sql`:

```bash
docker compose down -v
docker compose up --build
```

> `docker compose down -v` elimina deliberadamente todos los datos almacenados por esta práctica.

### Sin Docker

Use una instancia PostgreSQL local y configure `DATABASE_URL` para el backend. Luego, en terminales separadas:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

```bash
cd frontend
npm ci
npm run dev
```

Vite reenvía `/api` a `BACKEND_HOST_URL`. En ejecución local su valor predeterminado es `http://localhost:8000`; dentro de Compose se resuelve como `http://backend:8000`. Para omitir el proxy, use `VITE_API_URL=http://localhost:8000/api npm run dev`. Las dependencias locales no se versionan; `.gitignore` excluye los directorios generados.

## Recorrido del modelo

1. **Organizaciones**: cree el contenedor de propiedad del ejemplo.
2. **Ubicaciones**: use el ID de una organización. El par organización/nombre es único.
3. **Dispositivos**: use el mismo ID de organización. El número de serie es único globalmente.
4. **Mediciones**: use el ID de un dispositivo. Cada medición se asocia directamente al dispositivo: no hay entidad `Sensor`.

Los historiales de estado y ubicación están en el esquema para estudiar intervalos temporales. No tienen UI ni endpoints en esta primera porción porque el objetivo es reconocer el diseño físico, no adelantar extensiones.

## Restricciones que conviene verificar

| Regla | Implementación |
| --- | --- |
| Ocho tablas acordadas | `docs/modeling/physical.sql` define el esquema y `app/models.py` mantiene su representación para el backend |
| Una ubicación actual por dispositivo | Índice parcial `device_location_one_current_idx` |
| Un estado actual por dispositivo | Índice parcial `device_status_one_current_idx` |
| Historial consultable eficiente | Índice `measurements_device_recorded_at_idx` |
| Coordenadas válidas | `CHECK` para latitud y longitud |
| Intervalo temporal válido | `ended_at > started_at` cuando existe |

## Verificación

Desde `clase-02/practica`:

```bash
(cd backend && pytest)
(cd frontend && npm run typecheck && npm test && npm run build)
```

## Visualizar y regenerar los diagramas

Los archivos SVG se abren directamente desde el explorador del repositorio o en cualquier navegador. Las fuentes `.mmd` pueden previsualizarse con una extensión Mermaid del editor. El modelo físico es el script SQL ejecutable y no necesita una imagen separada.

Para regenerar las vistas conceptual y lógica:

```bash
cd docs/modeling
for diagram in conceptual logical; do
  npx -y @mermaid-js/mermaid-cli@11.12.0 -i "$diagram.mmd" -o "$diagram.svg" -b transparent
done
```

## Fuera de alcance

No agregue autenticación, roles de acceso, RLS, `TenantContext`, entidad `Sensor`, PostGIS, TimescaleDB o pgVector. Son decisiones que exigen requisitos adicionales y pertenecen a clases posteriores.
