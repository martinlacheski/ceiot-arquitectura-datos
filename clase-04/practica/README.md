# Práctica autónoma de modelado, índices y evolución de esquema

Esta práctica individual ofrece ejemplos SQL **completamente resueltos** para ejecutar, observar y modificar libremente. No son ejercicios evaluativos ni se entrega una solución: cada consulta canónica ya es runnable. El entorno es independiente de Clase 3 y arranca desde una tabla plana deliberadamente **desnormalizada**, `registro_ambiental`, que se normaliza paso a paso durante el recorrido. Se concentra en PostgreSQL y pgAdmin; esta clase no incluye un cliente Python.

## Camino rápido con pgAdmin

1. Desde `clase-04/practica`, copie la configuración de ejemplo: `cp .env.example .env`.
2. Inicie PostgreSQL y pgAdmin: `docker compose up -d`.
3. Abra [http://localhost:5052](http://localhost:5052).
4. Inicie sesión con `student@example.edu` / `class4-local` (o sus valores de `.env`).
5. Registre el servidor descrito abajo y abra **Tools → Query Tool**.
6. Ejecute los archivos de [`sql/`](sql/) en orden. Puede seleccionar una sentencia o ejecutar el archivo completo.

> La interfaz principal es pgAdmin. La terminal solo se usa para iniciar los servicios.

## Abrir los scripts sin copiar y pegar

El directorio [`sql/`](sql/) queda accesible desde ambos contenedores, para no tener que pegar el contenido a mano en pgAdmin:

- **Desde pgAdmin (Query Tool → ícono de carpeta "Open File"):** los archivos aparecen directamente en la raíz del diálogo, ya logueado con `student@example.edu` (o el email que hayas puesto en `.env`; ver nota abajo). Seleccioná uno y ejecutalo con ▶ o F5.
- **Desde la terminal, dentro del contenedor `postgres`:**

  ```bash
  # Ejecutar un archivo completo:
  docker compose exec postgres psql -U ceiot -d ceiot_class4 -f /sql/01-dependencias-y-redundancia.sql

  # O entrar a una sesión interactiva y usar \i para cargar archivos uno por uno:
  docker compose exec postgres psql -U ceiot -d ceiot_class4
  ceiot_class4=# \i /sql/02-normalizacion.sql
  ```

  Ajustá `-U`/`-d` si cambiaste `POSTGRES_USER`/`POSTGRES_DB` en `.env`.

> El montaje de pgAdmin depende del email de login: la carpeta interna es `/var/lib/pgadmin/storage/<email con solo el "@" reemplazado por "_">` (el "." se conserva; confirmado inspeccionando el contenedor en ejecución). Si cambiás `PGADMIN_DEFAULT_EMAIL` en `.env`, actualizá el nombre de esa carpeta en `docker-compose.yml` para que coincida.
>
> Si ya habías levantado los contenedores antes de este cambio, corré `docker compose up -d` de nuevo para que pgAdmin tome el nuevo volumen (no hace falta borrar `pgadmin_data`, tus conexiones guardadas se mantienen).

## Conectar pgAdmin a PostgreSQL

En pgAdmin, haga clic derecho en **Servers → Register → Server...**:

| Pestaña/campo | Valor predeterminado |
| --- | --- |
| General → Name | `ceiot-clase-04` |
| Connection → Host name/address | `postgres` |
| Connection → Port | `5432` |
| Connection → Maintenance database | `ceiot_class4` |
| Connection → Username | `ceiot` |
| Connection → Password | `ceiot` |

`postgres` es el nombre interno del servicio Compose; dentro de pgAdmin no use `localhost`. Después, abra **Databases → ceiot_class4 → Schemas → public → Tables** para reconocer el esquema.

La inicialización solo crea `registro_ambiental` (el punto de partida desnormalizado) con **20 filas**: 2 organizaciones (FIUBA, TechCorp), 4 ubicaciones (2 por organización) y 5 dispositivos, cada uno con 4 lecturas. Cada fila empaqueta entre 2 y 3 variables separadas por comas en `variables`/`valores`. Al ejecutar `sql/02-normalizacion.sql` esas 20 filas se desdoblan en exactamente **50 mediciones individuales**, repartidas así por dispositivo:

| dispositivo_id | nombre | numero_serie | ubicación | organización | mediciones |
| --- | --- | --- | --- | --- | --- |
| 15 | Ambiente 01 | AMB-15-01 | Aula 204 | FIUBA | 10 |
| 16 | Ambiente 02 | AMB-16-01 | Aula 204 | FIUBA | 8 |
| 17 | Ambiente 03 | AMB-17-01 | Laboratorio 101 | FIUBA | 12 |
| 18 | Planta 01 | PLT-18-01 | Planta Norte | TechCorp | 10 |
| 19 | Depósito 01 | DEP-19-01 | Depósito Sur | TechCorp | 10 |

Comprobación rápida en Query Tool (antes de normalizar):

```sql
SELECT COUNT(*) AS filas_denormalizadas FROM registro_ambiental;
```

El resultado esperado es `20`. Después de ejecutar `sql/02-normalizacion.sql`:

```sql
SELECT COUNT(*) AS mediciones_totales FROM mediciones;
```

El resultado esperado es `50`.

## Recorrido progresivo

Cada archivo sigue el mismo ritmo: **contexto → ejemplo ejecutable → observación esperada → variaciones seguras → recuperación** (cuando aplica). Las variaciones son invitaciones para jugar; no hay consignas pendientes, espacios en blanco, TODO ni soluciones ocultas.

| Orden | Archivo | Qué observar |
| --- | --- | --- |
| 1 | [`01-dependencias-y-redundancia.sql`](sql/01-dependencias-y-redundancia.sql) | Redundancia observable, dependencias funcionales, anomalías de actualización/borrado, violación de 1FN |
| 2 | [`02-normalizacion.sql`](sql/02-normalizacion.sql) | Derivación guiada 1FN → 2FN → 3FN: crea y puebla `organizaciones`, `ubicaciones`, `dispositivos`, `mediciones` con verificación de conteos en cada etapa |
| 3 | [`03-desnormalizacion-justificada.sql`](sql/03-desnormalizacion-justificada.sql) | `dispositivos.medicion_count` como excepción deliberada; demuestra el riesgo de desincronización y lo revierte |
| 4 | [`04-indices.sql`](sql/04-indices.sql) | Índice simple vs. compuesto sobre `mediciones`, orden de columnas, selectividad alta (`numero_serie`) vs. baja (`variable`) |
| 5 | [`05-planes-de-ejecucion.sql`](sql/05-planes-de-ejecucion.sql) | EXPLAIN / EXPLAIN ANALYZE: mide **antes** (sin índices) y **después** (con los índices de 04) el mismo patrón de consulta frecuente |
| 6 | [`06-vistas.sql`](sql/06-vistas.sql) | `CREATE VIEW mediciones_con_contexto`, `CREATE MATERIALIZED VIEW resumen_mediciones`, `REFRESH MATERIALIZED VIEW` y la diferencia de actualidad entre ambas |
| 7 | [`07-json-y-jsonb.sql`](sql/07-json-y-jsonb.sql) | `dispositivos.configuracion JSONB`, lectura con `->>`, filtros con `@>`, cuándo JSONB es apropiado y cuándo no |
| 8 | [`08-evolucion-del-esquema.sql`](sql/08-evolucion-del-esquema.sql) | `ALTER TABLE ... ADD COLUMN firmware_version`, backfill parcial sobre datos existentes, changelog conceptual v1→v5 |

**Secuencia de índices y planes (4 → 5):** `04-indices.sql` crea el índice simple `mediciones_dispositivo_id_idx` y el compuesto `mediciones_dispositivo_id_timestamp_idx`. `05-planes-de-ejecucion.sql` elimina ambos al empezar (para reproducir el "antes" real, sin índices), mide con EXPLAIN ANALYZE, los vuelve a crear igual que 04 y vuelve a medir el "después". Al terminar 05, el estado de los índices es el mismo que si solo se hubiera ejecutado 04.

Los archivos 1, 4 y parte de 7-8 (lecturas) son de solo lectura o solo agregan objetos nuevos. Los archivos 2, 6 y 7 crean tablas, vistas o columnas que quedan permanentes (son la base para los siguientes). Los archivos 3, 5 y 6 incluyen bloques de demostración que insertan una fila o cambian una configuración de sesión y la revierten dentro del mismo archivo, dejando los conteos documentados arriba intactos. Los archivos 7 y 8 evolucionan el esquema hacia adelante a propósito (ese es su punto pedagógico) y no están pensados para revertirse.

## Cómo experimentar sin perder el punto de partida

- Ejecute primero la consulta canónica y compare con **OBSERVACIÓN ESPERADA**.
- Cambie un `dispositivo_id`, una variable o un rango de fechas usando las **VARIACIONES SEGURAS**.
- `database/02-seed.sql` y `sql/02-normalizacion.sql` son **idempotentes**: pueden ejecutarse varias veces sin duplicar filas ni fallar por objetos ya existentes (`CREATE TABLE IF NOT EXISTS`, `ON CONFLICT DO NOTHING`, bloques `DO` que ignoran restricciones repetidas).
- Antes y después de cualquier bloque de demostración, confirme `SELECT COUNT(*) FROM mediciones;`: debe seguir en `50`.
- Si interrumpe `05-planes-de-ejecucion.sql` a mitad de camino, ejecute `SET enable_seqscan = on;` para restaurar el planificador antes de seguir trabajando en esa misma sesión.
- Para recrear el entorno desde cero, elimine los volúmenes (`docker compose down -v`) y vuelva a levantar los contenedores.

El objetivo es explorar el efecto de normalizar, indexar y evolucionar un esquema real, no resolver desafíos ni entregar respuestas.

## Mapa del entorno

| Ruta | Responsabilidad |
| --- | --- |
| [`docker-compose.yml`](docker-compose.yml) | PostgreSQL y pgAdmin |
| [`database/01-schema.sql`](database/01-schema.sql) | Crea únicamente `registro_ambiental`, el punto de partida desnormalizado |
| [`database/02-seed.sql`](database/02-seed.sql) | Seed determinista e idempotente: 20 filas de `registro_ambiental` |
| [`sql/`](sql/) | Ejemplos SQL progresivos y resueltos: normalización, desnormalización, índices, planes, vistas, JSONB y evolución de esquema |

Los volúmenes `postgres_data` y `pgadmin_data` conservan base y configuración entre reinicios. Los scripts de `database/` se ejecutan solo al crear por primera vez el volumen de PostgreSQL; las tablas normalizadas, vistas, índices y columnas nuevas se crean manualmente ejecutando `sql/` en orden desde pgAdmin.

## Lista de comprobación

- [ ] pgAdmin conecta con el host `postgres`.
- [ ] `SELECT COUNT(*) FROM registro_ambiental;` devuelve `20` antes de normalizar.
- [ ] Después de `02-normalizacion.sql`: `organizaciones` tiene `2` filas, `ubicaciones` tiene `4`, `dispositivos` tiene `5` y `mediciones` tiene `50`.
- [ ] En `05-planes-de-ejecucion.sql`, la Parte 1 (sin índices) muestra un nodo `Seq Scan` en el plan.
- [ ] En `05-planes-de-ejecucion.sql`, la Parte 2 con `enable_seqscan = off` muestra un nodo `Index Scan` sobre `mediciones_dispositivo_id_timestamp_idx`.
- [ ] `resumen_mediciones` refleja una medición nueva recién después de `REFRESH MATERIALIZED VIEW`, no antes.
- [ ] Después de `08-evolucion-del-esquema.sql`, exactamente `3` dispositivos tienen `firmware_version` no nulo y `2` quedan pendientes.
- [ ] Los ocho scripts de `sql/` se ejecutan en orden sin completar código faltante.
