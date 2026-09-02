# Práctica: del requerimiento al modelo IoT ejecutable

Esta práctica conecta tres vistas del mismo caso: requisitos y diagramas, DDL PostgreSQL y una API/UI mínima para crear y listar organizaciones, ubicaciones, dispositivos y mediciones.

## Camino rápido

1. Copie `.env.example` como `.env` y ajuste los valores locales si fuera necesario.
2. Ejecute `docker compose up --build` desde este directorio.
3. Abra `http://FRONTEND_PUBLIC_HOST:FRONTEND_HOST_PORT`, cree una organización y selecciónela después al crear ubicaciones o dispositivos. La UI conserva el recurso activo en `?resource=`.
4. Consulte `http://BACKEND_PUBLIC_HOST:BACKEND_HOST_PORT/api/docs` para inspeccionar la API y `http://BACKEND_PUBLIC_HOST:BACKEND_HOST_PORT/health` para comprobar la disponibilidad.

Con los valores predeterminados, puede acceder directamente a:

- [Frontend — aplicación IoT](http://localhost:5173)
- [Backend — estado de la API](http://localhost:8000/health)
- [Backend — documentación interactiva](http://localhost:8000/api/docs)
- [Backend — organizaciones](http://localhost:8000/api/organizations)

Si modifica `BACKEND_HOST_PORT` o `FRONTEND_HOST_PORT` en `.env`, ajuste estas URLs según corresponda.

> La práctica no implementa login, autorización, RLS ni `TenantContext`. `organization_id` representa propiedad del dominio y permite relacionar ejemplos; no es una frontera de seguridad.

## API y rutas

Los recursos de la API usan el prefijo `/api`: por ejemplo, `GET /api/organizations` y `POST /api/measurements`. La comprobación de disponibilidad canónica no lleva prefijo: `GET /health`; la cabecera de la UI muestra su estado. El navegador llama a `/api` y `/health`, y Vite conserva esas rutas al reenviarlas hacia `BACKEND_HOST_URL`. Dentro de Compose, esa URL se resuelve como `http://backend:8000`; no debe incluir `/api`, porque la solicitud ya contiene ese prefijo. Si la UI sigue mostrando errores de proxy después de cambiar esa configuración, reconstruya la imagen con `docker compose up --build` para no conservar una configuración Vite anterior.

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

PostgreSQL inicializa el esquema con `docs/modeling/physical.sql` y después carga los datos de muestra desde `database/sql/02-seed.sql`. El seed determinista crea dos organizaciones, cuatro ubicaciones, tres dispositivos por organización y 72 mediciones distribuidas durante 14 fechas; los IDs estables y `ON CONFLICT` permiten volver a ejecutarlo sin duplicar sus registros. Los pares `POSTGRES_BIND_HOST`/`POSTGRES_HOST_PORT`, `BACKEND_BIND_HOST`/`BACKEND_HOST_PORT` y `FRONTEND_BIND_HOST`/`FRONTEND_HOST_PORT` controlan las interfaces y puertos publicados. `BACKEND_PUBLIC_HOST` y `FRONTEND_PUBLIC_HOST` se usan para las URLs que abre el navegador. Dentro de la red de contenedores, los servicios conservan sus nombres y puertos internos (`postgres:5432`, `backend:8000` y `frontend:5173`).

### Comprobar la instalación

En una instalación limpia, `docker compose up --build` crea el volumen de PostgreSQL, ejecuta primero `docs/modeling/physical.sql` y después carga `database/sql/02-seed.sql`.

Comprobar que el backend utiliza la base creada:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/organizations
```

La primera respuesta debe informar `{"status":"ok","database":"connected"}` y la segunda debe devolver las organizaciones cargadas por el archivo de datos de muestra.

### Reiniciar la práctica si ya existía un volumen

Este paso no es necesario para volver a aplicar el seed estable sobre una base existente. Utilícelo solamente cuando necesite descartar una base anterior y volver a ejecutar `physical.sql` desde cero:

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
2. **Ubicaciones**: selecciónelas desde una organización existente. El par organización/nombre es único.
3. **Dispositivos**: seleccione primero la organización y luego una ubicación de esa organización. El alta valida esa pertenencia y, en una única transacción, crea el dispositivo junto con su intervalo inicial en `device_location_history`; el inicio usa la fecha de instalación o el instante UTC actual. El número de serie es único globalmente.
4. **Mediciones**: seleccione un dispositivo. Cada medición se asocia directamente al dispositivo: no hay entidad `Sensor`.

`device_location_history` es la única fuente de verdad para la ubicación actual e histórica: `devices` no guarda un `location_id`. El listado de dispositivos consulta el intervalo abierto y muestra su ubicación actual. Los historiales de estado permanecen en el esquema para estudiar intervalos temporales; esta práctica no incorpora todavía su UI ni endpoints de cambios posteriores.

## Restricciones que conviene verificar

| Regla | Implementación |
| --- | --- |
| Ocho tablas acordadas | `docs/modeling/physical.sql` define el esquema y `app/models.py` mantiene su representación para el backend |
| Una ubicación actual por dispositivo | Índice parcial `device_location_one_current_idx` |
| Un estado actual por dispositivo | Índice parcial `device_status_one_current_idx` |
| Historial consultable eficiente | Índice `measurements_device_recorded_at_idx` |
| Coordenadas válidas | `CHECK` para latitud y longitud |
| Intervalo temporal válido | `ended_at > started_at` cuando existe |

## Fundación del frontend

La UI de Clase 2 usa Tailwind CSS v4 y componentes locales estilo shadcn con tokens semánticos y tipografía Montserrat. Cada recurso conserva una sola pestaña activa en la URL y presenta un espacio de trabajo con tabla TanStack, formulario y feedback accesible.

- La tabla pagina en cliente, permite elegir el tamaño de página y navegar a primera, anterior, siguiente o última página; la instancia admite evolucionar a paginación de servidor mediante `totalItems`.
- La barra de herramientas busca texto y filtra ubicaciones/dispositivos por organización. En mediciones, los filtros de organización, ubicación actual, dispositivo y fechas se intersectan en el cliente al asociar cada medición con los dispositivos ya cargados. Es una decisión pedagógica para estudiar relaciones y filtros compuestos con un seed pequeño; evita consultas adicionales y no sustituye filtros paginados y autorizados en el servidor para conjuntos de datos reales. Los selectores relacionados son buscables.
- Al crear un registro, la UI vuelve a cargar la lista y muestra confirmación; errores de carga o alta exponen reintento. Para dispositivos, primero se elige la organización y recién entonces una ubicación perteneciente a ella.
- El proxy de Vite mantiene `/api` y `/health` hacia `BACKEND_HOST_URL`.

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
