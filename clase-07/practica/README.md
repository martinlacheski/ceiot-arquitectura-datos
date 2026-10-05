# Práctica autónoma de administración, seguridad y escalabilidad de bases de datos

Esta práctica evoluciona el sistema de la Clase 6 (TimescaleDB, PostGIS, pgvector, Redis, SeaweedFS, RAG y Text-to-SQL) en lugar de empezar de cero. En la primera parte lo volvés **multi-tenant y seguro**: dos organizaciones comparten las mismas tablas, cada una ve sólo lo suyo, y la IA (Text-to-SQL y RAG) hereda ese mismo aislamiento (filminas 70–74). En la segunda parte operás la base: concurrencia, respaldos, monitoreo, particionamiento, replicación y escalabilidad (filminas 40–68). Todo el recorrido está resuelto y es no evaluativo: ejecutá el camino rápido y después explorá cada tema con los comandos de la tabla.

**Idea central:** la seguridad no pertenece a la interfaz ni al modelo de IA, forma parte de la arquitectura de datos. La base decide qué filas ve cada usuario (Row Level Security) y todo lo demás lo hereda.

```text
Usuario ─► identidad / tenant ─► Aplicación ─┬─► Text-to-SQL ─┐
                                             └─► RAG ─────────┴─► PostgreSQL (RLS + pgvector) ─► datos autorizados
```

## Requisitos

- Docker con Docker Compose v2 (`docker compose`) y `curl`.
- Unos **10 GB libres** para Docker: la imagen Python ocupa ~2 GB y el modelo `BAAI/bge-m3` ~4,3 GB (se descarga una sola vez, al subir tu primer PDF).
- Para la réplica y los experimentos de escalabilidad, unos GB y CPU extra: el segundo PostgreSQL usa hasta 2 CPU y 4 GB de memoria.
- Opcional: una clave de [OpenRouter](https://openrouter.ai/) para Text-to-SQL, RAG con respuesta redactada y el modo integrado.

## Servicios y URLs

Todos los puertos se publican sólo en `127.0.0.1` y se pueden cambiar en `.env` (columna Variable). Los puertos son distintos de los de la Clase 6, así que ambas prácticas pueden convivir (ver [Problemas frecuentes](#problemas-frecuentes)).

| Servicio | URL desde tu máquina | Credenciales (por defecto) | Variable | Para qué |
| --- | --- | --- | --- | --- |
| Aplicación web | [http://127.0.0.1:8007/](http://127.0.0.1:8007/) | — (elegís un usuario simulado en la UI) | `APP_PORT` | Carga de PDF y consultas RAG / Text-to-SQL / Integrado; API en `/api/query`, salud en `/health` |
| pgAdmin | [http://127.0.0.1:5057/](http://127.0.0.1:5057/) | `student@example.edu` / `class7-local` | `PGADMIN_PORT` | Explorar tablas, ejecutar los scripts SQL y ver el Dashboard (sesiones y candados) |
| PostgreSQL | `postgresql://ceiot:ceiot_local_only@127.0.0.1:5437/ceiot_class7` | `ceiot` / `ceiot_local_only` (dueño) | `POSTGRES_PORT` | TimescaleDB, PostGIS y pgvector (desde pgAdmin usá el host `postgres` y el puerto `5432`) |
| PostgreSQL réplica | `postgresql://ceiot:ceiot_local_only@127.0.0.1:5438/ceiot_class7` | las mismas | `POSTGRES_REPLICA_PORT` | Sólo con `--profile replica`: copia de sólo lectura por streaming |
| RedisInsight | [http://127.0.0.1:5541/](http://127.0.0.1:5541/) | — (la conexión `ceiot-clase-07` ya viene configurada) | `REDISINSIGHT_PORT` | Cliente web de Redis: ver claves, valores y TTL |
| Redis | `redis://:ceiot_redis_local_only@127.0.0.1:6380/0` | contraseña `ceiot_redis_local_only` (administrador) | `REDIS_PORT` | Copia temporal del último estado, con un namespace por organización |
| SeaweedFS S3 | `http://127.0.0.1:18334` | sin autenticación | `SEAWEEDFS_S3_PORT` | Endpoint S3 para clientes como `aws s3 --endpoint-url` |
| SeaweedFS filer | [http://127.0.0.1:18889/buckets/](http://127.0.0.1:18889/buckets/) | sin autenticación | `SEAWEEDFS_FILER_PORT` | Navegar los buckets y ver los PDF subidos, separados por organización |
| SeaweedFS master | [http://127.0.0.1:19334/](http://127.0.0.1:19334/) | sin autenticación | `SEAWEEDFS_MASTER_PORT` | Estado del clúster de un solo nodo |

Dentro de la red de Compose los puertos no cambian (`postgres:5432`, `redis:6379`). El servicio interno `uploader` (indexa los PDF subidos) no publica puerto.

### Roles y credenciales del laboratorio

Todas son **exclusivas de este laboratorio local**; no las reutilices.

| Rol | Contraseña | Quién lo usa | Qué puede |
| --- | --- | --- | --- |
| `ceiot` | `ceiot_local_only` | Vos, como dueño y administrador (scripts, pgAdmin, loader) | Todo; es superusuario, así que **ignora RLS** |
| `app_iot` | `ceiot_app_iot_local_only` | La aplicación de telemetría (se prueba con `SET ROLE` en los ejemplos) | Leer catálogos, insertar mediciones, cambiar sólo `sampling_interval_seconds` |
| `ai_readonly` | `ceiot_ai_readonly_local_only` | Text-to-SQL | Sólo `SELECT`, con RLS |
| `rag_readonly` | `ceiot_rag_readonly_demo_only` | RAG (búsqueda vectorial) | Sólo `SELECT` sobre documentos y fragmentos, con RLS |
| `rag_ingest` | `ceiot_rag_ingest_demo_only` | `uploader` (indexación) | Insertar documentos y fragmentos de la organización indicada |
| `replicator` | `ceiot_replicator_local_only` | La réplica | Sólo replicación (no lee tablas) |
| Redis `tenant_1` / `tenant_2` | `ceiot_redis_tenant1_local_only` / `ceiot_redis_tenant2_local_only` | Consumidores por organización | Leer (`GET`, `TTL`, `EXISTS`) sólo `iot:org-1:*` / `iot:org-2:*` |

## Camino rápido

Todos los comandos parten del directorio de la práctica (`cd clase-07/practica`).

1. Creá la configuración local sin pisar una existente:

   ```bash
   test -e .env || cp .env.example .env
   ```

2. Levantá los servicios y esperá a que estén saludables:

   ```bash
   docker compose --env-file .env -f compose.yaml up -d --build --wait
   ```

   Levanta PostgreSQL, Redis, SeaweedFS, pgAdmin, RedisInsight, `uploader` y la aplicación. Comprobá con `docker compose --env-file .env -f compose.yaml ps`: los servicios con healthcheck deben figurar `healthy`. La base arranca con el esquema, los roles y las políticas, pero **sin datos**. La réplica no arranca acá: es opcional (ver la sección 10 del recorrido, Replicación).

3. Cargá las dos organizaciones con sus ubicaciones, dispositivos y mediciones (el script ya está montado en `/lab/seed`):

   ```bash
   docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/seed/01-iot.sql'
   ```

   Al final debe mostrar `organization_count` igual a 2 y una fila por organización:

   | Organización | Ubicaciones | Dispositivos | Mediciones |
   | --- | --- | --- | --- |
   | 1 — Organización A — Facultad | 3 | 4 | 104 (o más, ver abajo) |
   | 2 — Organización B — Planta | 1 | 2 | 144 (o más, ver abajo) |

   Repetir el seed en otra hora agrega mediciones recientes, por eso "o más". En el esquema, `organization_id` cumple el rol del `tenant_id` de las filminas.

4. Copiá el último estado de cada equipo a Redis, en el namespace de su organización:

   ```bash
   docker compose --env-file .env -f compose.yaml run --rm loader
   ```

   Imprime cinco líneas `Proyección verificada: iot:org-N:last-known:<equipo>, Redis TTL=3600s` (tres de `org-1` y dos de `org-2`).

5. Comprobá la API y abrí la UI en [http://127.0.0.1:8007/](http://127.0.0.1:8007/):

   ```bash
   curl --fail http://127.0.0.1:8007/health
   ```

   Responde `{"status":"ok"}`. En **Usuario simulado → Consultar como** elegí **Ana — Organización A** o **Bruno — Organización B**.

6. Subí un PDF real como Ana o Bruno (ver [Documentos por organización](#documentos-por-organización-pdf-reales)). **No hay manuales de ejemplo**: son los PDF que cargues vos. La primera carga descarga `BAAI/bge-m3` (~4,3 GB) y puede tardar varios minutos.

7. (Opcional) Registrá el servidor en pgAdmin, como se explica a continuación.

> **Clave de OpenRouter:** Text-to-SQL, el modo Integrado y RAG (cuando hay evidencia y debe redactar la respuesta) la necesitan. Escribila sólo en `OPENROUTER_API_KEY` de `clase-07/practica/.env` (no se versiona; si la tenías en el `.env` de la Clase 6, copiala a mano) y recreá la app con `docker compose --env-file .env -f compose.yaml up -d --build`. Cada llamada puede tener costo y envía tu pregunta y el contexto al proveedor: no uses datos personales ni sensibles. No pegues la clave en chats ni issues. Revisá siempre el SQL, las filas y las fuentes, no sólo la prosa del modelo.

## Conectar pgAdmin

1. Abrí [http://127.0.0.1:5057/](http://127.0.0.1:5057/) e ingresá con `student@example.edu` / `class7-local`.
2. Clic derecho en **Servers → Register → Server...**
3. Pestaña **General**: nombre `Clase 7`.
4. Pestaña **Connection**:

   | Campo | Valor |
   | --- | --- |
   | Host name/address | `postgres` |
   | Port | `5432` |
   | Maintenance database | `ceiot_class7` |
   | Username | `ceiot` |
   | Password | `ceiot_local_only` (podés marcar **Save password**) |

5. Guardá y abrí **Databases → ceiot_class7 → Schemas → public**: tablas `organizations`, `locations`, `devices`, `measurements`, `manual_documents` y `manual_chunks`, y las vistas `lab_read.*` que usa Text-to-SQL. En **Properties → Comment** de cada tabla y columna está la documentación que el sistema le pasa al modelo.

`postgres` es el nombre del servicio dentro de la red de Compose: desde pgAdmin **no** uses `localhost` ni `5437`. Para la réplica registrá otro servidor con host `postgres-replica` y puerto `5432`. Si usás un cliente desde tu máquina (DBeaver, `psql` local), conectá a `127.0.0.1:5437` (réplica: `5438`).

> **Ojo:** conectado como `ceiot` ves **todas** las organizaciones, porque el superusuario ignora RLS. Para ver lo que ve una organización usá `SET ROLE app_iot` y fijá el tenant, como en `02-rls.sql`.

## Ejecutar los scripts

Los scripts están montados como sólo lectura dentro de los contenedores, así no hace falta copiar y pegar:

| Carpeta del repositorio | Dentro de `postgres` y `pgadmin` | Dentro de `postgres-replica` | Dentro de `redis` |
| --- | --- | --- | --- |
| [`postgres/seed/`](postgres/seed/) | `/lab/seed` | — | — |
| [`postgres/examples/`](postgres/examples/) | `/lab/examples` | `/lab/examples` | — |
| [`examples/`](examples/) | — | — | `/lab/examples` |

**Desde pgAdmin:** en el Query Tool usá el ícono de carpeta (**Open File**) y elegí el almacenamiento compartido `examples` o `seed`. Abrí el archivo y ejecutalo con ▶ o F5. Las carpetas son de sólo lectura: si modificás un script, guardalo en **My Storage**. Los scripts de concurrencia usan `\prompt` y **no funcionan en pgAdmin**, sólo en `psql`.

**Desde el contenedor de PostgreSQL**, con `psql` (cambiá el nombre del archivo):

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/01-roles-permisos.sql'
```

O en forma interactiva, para ejecutar y modificar consultas:

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
ceiot_class7=# \i /lab/examples/02-rls.sql
```

Más abajo, cada comando se abrevia como `psql -f /lab/examples/<archivo>`: es siempre el comando anterior cambiando el archivo. Los `.sh` se ejecutan con `sh` (en el contenedor o desde el host, según indique cada sección).

**Redis y RedisInsight:** abrí [http://127.0.0.1:5541/](http://127.0.0.1:5541/), aceptá los términos la primera vez y entrá a la base `ceiot-clase-07`. En **Browser** buscá `iot:*` para ver las claves `iot:org-1:last-known:*` y `iot:org-2:last-known:*` con su JSON y TTL. Si la lista de bases aparece vacía, agregala a mano con host `redis`, puerto `6379` y la contraseña `ceiot_redis_local_only` (no uses `localhost`: RedisInsight corre en su propio contenedor). Esa conexión es del administrador y ve todo; los usuarios por organización sólo existen en `redis-cli` (ver la sección 5 del recorrido).

**SeaweedFS:** el filer en [http://127.0.0.1:18889/buckets/ceiot-manuales/](http://127.0.0.1:18889/buckets/ceiot-manuales/) muestra los PDF subidos desde la UI en `uploads/org-<id>/…`. También funciona como S3: `aws s3 ls s3://ceiot-manuales --recursive --endpoint-url http://127.0.0.1:18334 --no-sign-request`.

## Recorrido

Primero la **seguridad** (1–5, filminas 8–38 y 70–74) y después la **operación** (6–11, filminas 40–68). Podés hacerlos en cualquier orden, pero 1 y 2 explican los roles que usan los demás.

| # | Tema | Filminas | Comando o acción | Qué observar |
| --- | --- | --- | --- | --- |
| 1 | Roles y mínimo privilegio | 8–14 | `psql -f /lab/examples/01-roles-permisos.sql` | Matriz de privilegios; `app_iot` no puede `DELETE`, `CREATE TABLE`, ni cambiar `model` |
| 2 | Row Level Security | 23–29 | `psql -f /lab/examples/02-rls.sql` | Sin contexto: 0 filas; tenant 1 ve 4 equipos, tenant 2 ve 2; el `INSERT` cruzado es rechazado |
| 3 | Text-to-SQL protegido | 33–35, 72 | UI como Ana y como Bruno; `/api/sql-schema?user_id=ana` | Cada usuario ve sólo sus datos; el esquema que recibe el modelo es el de su organización |
| 4 | RAG protegido | 36–38, 73 | UI: subir un PDF como Ana y preguntar como Bruno | "No encontré evidencia…" sin llamar a OpenRouter |
| 5 | Redis por organización | 30 | `sh examples/03-redis.sh` | `GET` permitido para `tenant_1` en `org-1`; `NOPERM` en `org-2` y al escribir |
| 6 | Concurrencia | 40–47 | 3 terminales: `03-concurrencia-a.sql`, `-b.sql`, `-observar.sql` | Actualización perdida, `FOR UPDATE`, `REPEATABLE READ`, deadlock |
| 7 | Backup y restore | 49–53 | `04-backup-restore.sh`, `04-error-humano.sql`, `recuperar` | Los conteos coinciden; el borrado accidental se recupera |
| 8 | Monitoreo | 54–55 | `psql -f /lab/examples/05-monitoreo.sql` | `pg_stat_activity`, tamaños, `pg_stat_statements`, `VACUUM`, `EXPLAIN` |
| 9 | Particionamiento | 60–64 | `psql -f /lab/examples/06-particionamiento.sql` | Poda de particiones; `DETACH`+`DROP` vs `DELETE`; chunks de TimescaleDB |
| 10 | Replicación | 53, 56–59 | `--profile replica` y `examples/07-replicacion.sh` | `streaming`, lag, "una réplica no es un backup" |
| 11 | Escalabilidad | 65–68 | `examples/08-escalabilidad.sh` | Más CPU, más transacciones por segundo; las lecturas escalan con la réplica |

También quedan de la Clase 6 `01-temporal.sql` (hypertable y promedios), `02-spatial.sql` (PostGIS) y `04-vector.sql` (pgvector). Se ejecutan igual desde la carpeta de ejemplos, **como dueño**, así que ven ambas organizaciones. Con los datos de la Clase 7 verás: `802.5` y `812.0` ppm por minuto de `AIR-002`; el promedio de temperatura del Aula 204 en 24 h; con 30 m alrededor de `AIR-002` aparecen `AIR-002` (0 m) y `AMB-001` (~20 m); y `04-vector.sql` devuelve 0 filas hasta que subas un PDF.

---

### Parte 1: seguridad

#### 1. Roles y mínimo privilegio (filminas 8–14)

Ejecutá `psql -f /lab/examples/01-roles-permisos.sql`. El script corre como dueño y cambia de identidad con `SET ROLE` para mostrar qué puede cada rol; los rechazos se capturan y se imprimen como `NOTICE: Rechazado (...)`.

| Qué mirar | Resultado esperado |
| --- | --- |
| Matriz de privilegios | `app_iot` lee `organizations`, `locations` y `devices`, e inserta en `measurements`; `ai_readonly` sólo lee; **nadie** tiene `DELETE` |
| Privilegio por columna | `app_iot` puede cambiar `sampling_interval_seconds` (`t`) pero no `model` (`f`) |
| Operaciones rechazadas | `permission denied` en `DELETE`, `CREATE TABLE`, `UPDATE` de otra columna y `SELECT` en `measurements` |

Es repetible: las escrituras de la demo terminan en `ROLLBACK`.

#### 2. Row Level Security (filminas 23–29)

Ejecutá `psql -f /lab/examples/02-rls.sql`. Usa el rol `app_iot` y cambia el tenant con `set_config('app.tenant_id', ...)`.

| Paso | Resultado esperado |
| --- | --- |
| a. Sin contexto de tenant | 0 filas: la base **falla cerrada** |
| b. / c. Tenant 1 y tenant 2 | Tenant 1 ve `ACT-003`, `AIR-002`, `AMB-001`, `AMB-005`; tenant 2 ve `PLT-001`, `PLT-002` |
| d. Tenant 1 filtra `organization_id = 2` | 0 filas: el `WHERE` se suma a la política, nunca la reemplaza |
| e. `INSERT` de la organización 2 siendo tenant 1 | `Rechazado: new row violates row-level security policy for table "measurements"` |
| g. Como dueño `ceiot` | Ve todo (4 + 2 equipos, 104 + 144 mediciones): `es_superusuario = t` |
| h. Tablas con RLS | 6 tablas con `rowsecurity` y `forcerowsecurity` en `t`: `organizations`, `locations`, `devices`, `measurements`, `manual_documents`, `manual_chunks` |

Cómo está armado (ver [`postgres/init/07-tenant-rls.sql`](postgres/init/07-tenant-rls.sql)):

- Cada tabla con datos del tenant tiene `organization_id`, `ENABLE` y `FORCE ROW LEVEL SECURITY` y una política `tenant_isolation` que compara `organization_id` con `NULLIF(current_setting('app.tenant_id', true), '')::bigint`. Sin contexto da `NULL` y no devuelve filas.
- Las claves foráneas son compuestas (`organization_id`, id): una medición no puede apuntar a un equipo de otra organización.
- El **superusuario ignora RLS**, por eso la aplicación nunca se conecta como `ceiot`; usa roles sin privilegios de administrador.
- Las vistas `lab_read.*` usan `security_invoker`: se evalúan con los permisos (y la RLS) de quien consulta, no del dueño de la vista.

> **Lección importante:** `app.tenant_id` es un parámetro de configuración personalizado que **cualquier rol puede cambiar** con `set_config`. RLS no es mágica: la seguridad depende de que sólo el backend lo fije. Por eso el backend lo establece con `set_config(..., true)` dentro de la transacción, a partir del usuario autenticado, y el control previo del SQL generado por la IA rechaza `set_config`, `current_setting`, `dblink`, `query_to_xml` y funciones parecidas. Defensa en capas: la política, la identidad y la validación del SQL.

#### 3. Text-to-SQL protegido (filminas 33–35 y 72)

1. En la UI elegí **Ana**, modo **Consultar telemetría (Text-to-SQL)** y preguntá: `¿Cuál fue la temperatura promedio del Aula 204 durante las últimas 24 horas?`
2. Cambiá a **Bruno** y repetí la pregunta: el Aula 204 no existe para su organización.
3. Como Bruno, preguntá `Mostrame las mediciones de la otra organización.`: sólo obtiene filas de la Organización B.
4. Mirá el esquema que recibe el modelo: [`/api/sql-schema?user_id=ana`](http://127.0.0.1:8007/api/sql-schema?user_id=ana) y el de [`bruno`](http://127.0.0.1:8007/api/sql-schema?user_id=bruno). El descubrimiento corre **por tenant**: Ana nunca ve los nombres de la Organización B.

Cómo se protege el flujo:

| Capa | Qué hace |
| --- | --- |
| Identidad | La UI envía sólo `user_id`; el backend traduce `ana → org 1` y `bruno → org 2` ([`shared/tenants.py`](shared/tenants.py)). Si el cliente manda `tenant_id` u otro campo extra, la API responde `422` |
| Contexto | `set_config('app.tenant_id', ..., true)` dentro de la transacción de sólo lectura, antes de ejecutar el SQL generado |
| Rol | El SQL corre como `ai_readonly`: sólo `SELECT`, `statement_timeout` de 1,5 s, máximo 50 filas |
| Guarda de SQL | Rechaza más de una sentencia, escrituras y funciones que podrían tocar el contexto (`set_config`, `current_setting`, `dblink`, `query_to_xml`…) |
| RLS | Aun si el modelo escribiera `WHERE organization_id = 2`, la base devuelve 0 filas |

Probalo sin pasar por la UI (rechazo del `tenant_id` enviado por el cliente):

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8007/api/query \
  -H 'Content-Type: application/json' \
  -d '{"mode":"text-to-sql","question":"hola","user_id":"ana","tenant_id":2}'
```

Responde `422`. Las consultas con IA (modos `text-to-sql` e `integrated`) necesitan la clave de OpenRouter.

#### 4. RAG protegido (filminas 36–38 y 73)

Ver [Documentos por organización](#documentos-por-organización-pdf-reales) para subir los PDF. El recorrido:

1. Como **Ana**, subí un PDF (por ejemplo un datasheet) y esperá a que termine la indexación.
2. Como Ana, en modo **RAG**, elegí el documento y preguntá algo que su contenido responda: la respuesta cita página, sección y fuente.
3. Cambiá a **Bruno**: en **Documentos disponibles** no aparece el PDF de Ana.
4. Como Bruno, preguntá lo mismo en modo RAG (**Todos los documentos**): `No encontré evidencia suficiente…`, sin fuentes y **sin llamar a OpenRouter**, porque la búsqueda vectorial corre con RLS y los fragmentos de Ana nunca llegan al contexto.

La información no autorizada queda fuera del contexto *antes* de generar la respuesta: el filtrado lo hace la base, no el prompt.

#### 5. Redis y objetos por organización (filmina 30)

Redis no tiene RLS, así que el aislamiento se arma con **namespaces y ACL**:

- Las claves son `iot:org-<id>:last-known:<equipo>`. El `loader` es un proceso por lotes de **administrador**: lee todas las organizaciones y publica cada estado en su namespace.
- Cada organización tiene un usuario ACL (`tenant_1`, `tenant_2`) con `~iot:org-N:*` y sólo `GET`, `TTL` y `EXISTS`. No tiene `KEYS` ni `SCAN`, a propósito: `SCAN` ignora los patrones de clave y listaría los nombres de las claves de otras organizaciones.

```bash
sh examples/03-redis.sh
```

Se ejecuta desde el host (también sirve `docker compose --env-file .env -f compose.yaml exec redis sh /lab/examples/03-redis.sh`). Esperá: el `GET` de `iot:org-1:last-known:AIR-002` con su TTL; una clave de práctica con TTL de 20 s que se borra; y luego, como `tenant_1`, el `GET` propio permitido y dos errores `NOPERM` (leer `iot:org-2:last-known:PLT-001` y escribir).

Los PDF también se separan: viven en SeaweedFS bajo `uploads/org-<id>/…`, y el catálogo (`manual_documents`) está protegido por RLS.

---

### Parte 2: operación

Salvo que se indique otra cosa, los scripts de esta parte corren como dueño (`ceiot`) y **no tocan los datos de las organizaciones**, o los restauran al final.

#### 6. Concurrencia (filminas 40–47)

Necesitás **tres terminales** abiertas en `clase-07/practica`, con `psql` interactivo: usá `exec` **sin** `-T`. Todos los escenarios actúan sobre `sampling_interval_seconds` del equipo `AMB-001` (valor inicial 60) con el rol `app_iot` y el tenant 1.

| Terminal | Comando |
| --- | --- |
| A | `docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/03-concurrencia-a.sql'` |
| B | el mismo comando con `03-concurrencia-b.sql` |
| C | el mismo comando con `03-concurrencia-observar.sql` (sólo en el paso 8) |

Los pasos están numerados de 1 a 24 en todo el laboratorio. Antes de cada paso aparece una pausa (`PASO N (terminal X) ...`): seguí el orden de los números, alternando A y B, y apretá Enter cuando le toque a esa terminal.

| Escenario | Pasos | Qué debería pasar |
| --- | --- | --- |
| a. Actualización perdida | 1–5 | A y B leen 60; A escribe 30, B escribe 120 con su lectura vieja. Valor final **120**: el cambio de A se perdió sin error |
| b. `SELECT … FOR UPDATE` | 6–11 | B queda **esperando** (la terminal "se cuelga") hasta que A confirma; entonces lee 30 y escribe 40. Valor final **40**: se aplicaron los dos cambios |
| c. `REPEATABLE READ` | 12–17 | B recibe `could not serialize access due to concurrent update` en vez de pisar a A, reintenta y el valor final es **90** |
| d. Deadlock | 18–24 | A toma `AMB-001` y quiere `AIR-002`; B al revés. Tras `deadlock_timeout` (1 s) aparece `deadlock detected` en una de las dos (casi siempre B) |

En el **paso 8**, con B esperando, corré la terminal C. Verás una sesión `active` con `wait_event_type = Lock` (la de B), otra `idle in transaction` (la de A), y `pg_blocking_pids` indicando quién bloquea a quién. En pgAdmin podés ver lo mismo en **ceiot_class7 → Dashboard → Sessions / Locks**.

El paso 24 deja ambos equipos en 60. Si cerraste una terminal a medias y quedó otro valor, restauralo como dueño: `UPDATE devices SET sampling_interval_seconds = 60;`.

#### 7. Backup y restore (filminas 49–53)

El orden importa: **respaldo → error → recuperar**. Los comandos corren dentro del contenedor `postgres`:

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh /lab/examples/04-backup-restore.sh
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/04-error-humano.sql'
docker compose --env-file .env -f compose.yaml exec postgres sh /lab/examples/04-backup-restore.sh recuperar
```

| Paso | Qué hace | Resultado esperado |
| --- | --- | --- |
| 1. Respaldo | `pg_dump -Fc` al volumen `postgres_backups` | Un archivo comprimido `ceiot_class7.dump` |
| 2–3. Restauración | Base nueva `ceiot_class7_restored`; `timescaledb_pre_restore()`, `pg_restore`, `timescaledb_post_restore()` | `pg_restore terminó sin mensajes de error` |
| 4. Comparación | Filas por tabla, original vs restaurada | `OK: los conteos coinciden`; 6 políticas RLS restauradas |
| 5. Roles | `pg_restore -l` vs `pg_dumpall --roles-only` | 0 `CREATE ROLE` en el dump: **los roles no viajan**; hay que recrearlos aparte |
| Error humano | `DELETE` de las mediciones de `PLT-002` | El `DELETE` confirma de inmediato: no hay papelera ni `ROLLBACK` |
| `recuperar` | Rescata `PLT-002` de la base restaurada | `plt002_antes = 0` y `plt002_despues` con las filas recuperadas |

- **No repitas el respaldo después del error**: sobrescribiría el dump bueno con los datos ya borrados.
- El método sólo recupera lo que existía al momento del respaldo.
- El dump vive en el volumen `postgres_backups`, que sobrevive a `down` pero **no** a `down -v`.
- La aplicación (`app_iot`) no puede borrar mediciones: sólo el dueño pudo cometer este error, otra defensa de los roles.

#### 8. Monitoreo (filminas 54–55)

Antes de correrlo, hacé un par de preguntas Text-to-SQL como Ana y Bruno para que haya consultas que mostrar. Luego:

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/05-monitoreo.sql'
```

| Sección | Qué observar |
| --- | --- |
| 1. Conexiones | Sesiones por rol y estado; cuidado con `idle in transaction` |
| 2. Tamaños | `pg_total_relation_size` de una hypertable sólo cuenta el padre; el tamaño real lo da `hypertable_size()` |
| 3. `pg_stat_user_tables` | `seq_scan` alto con `idx_scan` bajo sugiere falta de índice; `n_dead_tup` indica trabajo pendiente de `VACUUM` |
| 4. `pg_stat_statements` | Las 10 consultas que más tiempo consumen, normalizadas; las de Text-to-SQL aparecen con el rol `ai_readonly` |
| 5. Filas muertas | Tras un `UPDATE` masivo `n_dead_tup` sube; `VACUUM` lo devuelve a 0 |
| 6. `EXPLAIN ANALYZE` | `Seq Scan` sin índice vs `Index Scan` con índice, con `Execution Time` y `Buffers` |

`pg_stat_statements` se habilita con parámetros `-c` en el `command` del servicio `postgres` de [`compose.yaml`](compose.yaml) (`shared_preload_libraries`, `pg_stat_statements.track`, `track_io_timing`), no editando `postgresql.conf`: ese archivo vive en el volumen y sólo se escribe al inicializarlo. En pgAdmin, **Dashboard** y **Statistics** muestran información equivalente. Es repetible: la tabla `lab_monitoring_demo` se crea y se borra dentro del script.

#### 9. Particionamiento (filminas 60–64)

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /lab/examples/06-particionamiento.sql'
```

Tarda unos 30 segundos: crea el esquema `lab_ops` (sólo del dueño; ningún rol de aplicación lo ve) con ~2,6 millones de filas sintéticas en una tabla común y otra particionada por mes.

| Sección | Qué observar |
| --- | --- |
| 1. Dos tablas | `measurements_archive` tiene 12 particiones (2025); `measurements_flat` es una sola tabla; ambas con 2.628.000 filas |
| 2. Consulta de un mes | **Poda de particiones**: el plan toca sólo `measurements_archive_2025_06` |
| 3. Particiones | 12 particiones de tamaño parecido, con su rango |
| 4. Retención | `DETACH PARTITION` + `DROP TABLE` tarda milisegundos y no deja filas muertas; el `DELETE` equivalente tarda unas diez veces más y deja `n_dead_tup` alto hasta el `VACUUM` (que además no achica el archivo) |
| 5. `LIST` por organización | Cada tenant en su tabla física; filtrar por `organization_id` poda la otra. Es otra forma de aislar, distinta de RLS |
| 6. TimescaleDB | La hypertable `measurements` ya está en chunks; `drop_chunks` es el `DETACH`+`DROP` automático (sobre una hypertable de práctica, no sobre tus datos) |
| 7. Permisos | `ai_readonly`, `rag_readonly`, `rag_ingest` y `app_iot` no pueden usar `lab_ops` (todo `f`) |

> **Resultado honesto:** en este laboratorio la consulta de **un mes** no es más rápida en la tabla particionada (del orden de 20–30 ms en ambas; el índice ya ayuda a la común y los datos están ordenados por fecha). El beneficio real del particionamiento está en la **retención y el mantenimiento** (sección 4), no en esta consulta aislada. Los tiempos exactos dependen de tu máquina.

Las tablas quedan creadas para explorarlas en pgAdmin (**ceiot_class7 → Schemas → lab_ops**). Para limpiar: `DROP SCHEMA lab_ops CASCADE;` (como dueño).

#### 10. Replicación en streaming (filminas 53 y 56–59)

La réplica es opcional y vive en un perfil de Compose. Levantala (clona el primario con `pg_basebackup` la primera vez; puede tardar un rato):

```bash
docker compose --env-file .env -f compose.yaml --profile replica up -d --wait
```

Después, el recorrido completo desde el host, que no destruye nada (las filas de demostración se borran y el borrado de `PLT-002` se recupera del respaldo):

```bash
sh examples/07-replicacion.sh
```

| Paso | Qué observar |
| --- | --- |
| a. Primario: `pg_stat_replication` | Una fila `walreceiver` con `state = streaming`, `sync_state = async` |
| b. Slot `replica_1` | `active = t`; el primario conserva el WAL que la réplica no leyó (acotado por `max_slot_wal_keep_size=1GB`) |
| c. Réplica: `pg_is_in_recovery()` | `t`; mismos datos y las 6 políticas RLS (viajan con el catálogo) |
| d. Escribir en la réplica | `cannot execute INSERT in a read-only transaction` |
| e. `INSERT` en el primario | Aparece en la réplica casi de inmediato |
| f. Lag con la réplica pausada | `lag_bytes` crece con cada escritura y vuelve a 0 al reanudar |
| g. Una réplica **no** es un backup | Tras el `DELETE` de `PLT-002`, el primario **y la réplica** quedan en 0; sólo el dump lo recupera |

También podés correr sólo la parte de lectura: `psql -f /lab/examples/07-replicacion.sql` en `postgres` y `07-replicacion-replica.sql` en el servicio `postgres-replica` (`exec postgres-replica sh -c '…'` con el mismo comando de `psql`).

**Failover manual (destructivo para la réplica).** Detiene el primario, promueve la réplica con `pg_promote()` y comprueba que el `INSERT`, que antes fallaba, ahora funciona:

```bash
sh examples/07-failover.sh
sh examples/07-failover.sh reset
```

`reset` descarta la réplica promovida, borra **sólo** su volumen (`postgres_replica_data`), arranca de nuevo el primario (su volumen nunca se toca) y la clona. Mientras no hagas `reset`, la aplicación sigue apuntando a `postgres`, que está caído: **nadie la redirige** a la réplica promovida. Eso lo hacen herramientas de orquestación como Patroni o repmgr, o un balanceador con health checks.

#### 11. Escalabilidad (filminas 65–68)

```bash
sh examples/08-escalabilidad.sh cpus-2
```

Se ejecuta desde el host. Crea una base `bench` con `pgbench -i -s 10` (~150 MB) y mide durante 20 s cada prueba (8 clientes, 4 hilos); tarda 2–3 minutos y agrega una fila a la tabla de resultados (`etiqueta | hora | tps primario | tps primario+réplica`).

1. **Vertical (filminas 65–66):** repetí con menos CPU. En `.env` poné `POSTGRES_CPUS=1`, aplicalo con `docker compose --env-file .env -f compose.yaml up -d postgres` (recrea el contenedor, los datos quedan) y corré `sh examples/08-escalabilidad.sh cpus-1`. Compará las filas. Al terminar, volvé a `POSTGRES_CPUS=2` y repetí el `up -d postgres`.
2. **Horizontal de lectura (filmina 67):** con la réplica levantada, el mismo script mide también la prueba de sólo lectura repartida entre primario y réplica, y muestra que una escritura contra la réplica falla (`read-only transaction`): **las escrituras siguen yendo sólo al primario**.
3. **Sharding (filmina 68):** no se implementa; repartir filas entre servidores por una clave como `organization_id` es el tema de la Clase 8.

Para borrar la base de pruebas: `sh examples/08-escalabilidad.sh limpiar`.

| Medición de referencia (orientativa) | Aproximadamente |
| --- | --- |
| Sólo lectura, primario con 2 CPU | ~61.000 tps |
| Sólo lectura, primario con 1 CPU | ~26.000 tps |
| Primario + réplica en paralelo | ~148.000 tps combinados |

Son valores de una máquina concreta; los tuyos van a variar mucho según tu CPU. Lo importante es la tendencia: más CPU, más tps; más réplicas de lectura, más lecturas por segundo; y ningún cambio para las escrituras. Antes de escalar, identificá el cuello de botella.

---

## Documentos por organización (PDF reales)

No hay manuales versionados: los documentos son **los PDF reales que subas** (manuales de sensores, datasheets del ESP32…), siempre a nombre del usuario elegido.

1. En [http://127.0.0.1:8007/](http://127.0.0.1:8007/) elegí el usuario en **Consultar como**.
2. En **Cargar e inspeccionar un PDF**, elegí un PDF con texto y presioná **Cargar PDF**. Debajo ves el progreso en vivo (`Indexando fragmento 12 de 93…`).
3. Revisá el resumen (`document_id`, SHA-256, páginas, chunks) y usá **Inspeccionar** en **Documentos disponibles**.
4. En **Nueva consulta** elegí **Consultar documentos (RAG)**, seleccioná el documento y preguntá.

Qué esperar con dos organizaciones:

- **El mismo PDF subido por Ana y por Bruno son dos documentos independientes**, cada uno en su prefijo `uploads/org-<id>/…` de SeaweedFS y con sus propios fragmentos.
- El listado y el detalle son por usuario: pedir el `document_id` de otra organización devuelve `404`.
- La primera indexación descarga `BAAI/bge-m3` (~4,3 GB) y tarda más.

La carga es local y no llama a OpenRouter; sólo la consulta posterior sí. Tamaño máximo: 50 MiB (`MAX_PDF_MIB`). Sólo procesa texto: no hace OCR ni acepta PDF cifrados. Cuesta unos 1,2 s por fragmento (un datasheet de ~90 fragmentos tarda un par de minutos). No hay borrado.

### Manual en inglés, pregunta en español

`BAAI/bge-m3` es multilingüe: permite preguntar en español sobre un manual en inglés.

1. Descargá un datasheet oficial, fuera del repositorio:
   - <https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf>
   - <https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf>
   - <https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
2. Subilo como Ana (o Bruno) y seleccionalo en modo RAG.
3. Preguntá en español, por ejemplo: `¿Qué corriente mínima debe entregar la fuente de alimentación?` o `¿Qué microcontrolador integra el módulo?`. El fragmento más cercano debería ser la sección en inglés correspondiente.

Si no recupera lo esperado, verificá que el documento quedó indexado y que elegiste el correcto. No subas el corte `0.55` para forzar coincidencias.

## Variables de entorno

Son opcionales y se definen en `.env`; si faltan, rige el valor por defecto. Tras cambiarlas, recreá los servicios con `docker compose --env-file .env -f compose.yaml up -d --build`.

| Variable | Por defecto | Qué controla |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | vacía | Clave para los modos con IA |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | Modelo que se consulta en OpenRouter |
| `OPENROUTER_MAX_COMPLETION_TOKENS` | `300` | Tope de tokens de salida por llamada |
| `MAX_PDF_MIB` | `50` | Tamaño máximo de un PDF (MiB) |
| `CHUNK_MAX_CHARS` / `CHUNK_OVERLAP_CHARS` | `1200` / `150` | Tamaño de fragmento y solape (el solape debe ser menor) |
| `EMBEDDING_BATCH_SIZE` | `4` | Fragmentos por lote al calcular embeddings |
| `RAG_MAX_COSINE_DISTANCE` | `0.55` | Distancia máxima aceptada en la recuperación |
| `RAG_MAX_TOP_K` | `4` | Máximo de fragmentos por consulta |
| `REDIS_TTL_SECONDS` | `3600` | Vida de las claves de Redis |
| `MANUAL_BUCKET` | `ceiot-manuales` | Bucket S3 de los documentos |
| `UPLOADER_CPUS` / `UPLOADER_MEM_LIMIT` | `2` / `4g` | Recursos del servicio que indexa PDF |
| `POSTGRES_CPUS` | `2` | Tope de CPU del primario y de la réplica (escalabilidad vertical) |
| `POSTGRES_MEM_LIMIT` | `4g` | Tope de memoria del primario y de la réplica |
| `APP_PORT`, `PGADMIN_PORT`, `REDISINSIGHT_PORT` | `8007`, `5057`, `5541` | Puertos publicados en `127.0.0.1` |
| `POSTGRES_PORT`, `POSTGRES_REPLICA_PORT`, `REDIS_PORT` | `5437`, `5438`, `6380` | Puertos de PostgreSQL, su réplica y Redis |
| `SEAWEEDFS_S3_PORT`, `SEAWEEDFS_FILER_PORT`, `SEAWEEDFS_MASTER_PORT` | `18334`, `18889`, `19334` | Puertos de SeaweedFS (S3, filer web y master) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `ceiot` / `ceiot_local_only` / `ceiot_class7` | Dueño y base; sólo se aplican al crear el volumen |
| `REDIS_PASSWORD` | `ceiot_redis_local_only` | Contraseña del administrador de Redis |
| `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` | `student@example.edu` / `class7-local` | Acceso a pgAdmin (se aplican al crear el volumen `pgadmin_data`) |

`MODELO_EMBEDDING` (`BAAI/bge-m3`) existe, pero no conviene cambiarlo: el esquema `VECTOR(1024)` y el corte coseno están calibrados para ese modelo.

## Experimentar sin perder el punto de partida

- Los ejemplos 01, 02, 05 y 07 (lectura), las consultas de la UI y `03-redis.sh` se pueden repetir libremente: las escrituras de la demo terminan en `ROLLBACK` o se borran solas.
- El seed y el loader se pueden repetir (el seed suma mediciones recientes). Si las claves de Redis expiraron, volvé a ejecutar `run --rm loader`.
- Los respaldos son repetibles, pero respetá el orden de la sección 7 (Backup y restore).
- `07-failover.sh` es destructivo para la réplica; `reset` la deja como antes.
- Para detener conservando datos, respaldos y caché del modelo: `docker compose --env-file .env -f compose.yaml down` (agregá `--profile replica` si la réplica está levantada).
- **`down -v` borra todo**: historial, Redis, PDF, **respaldos**, la réplica, el modelo descargado (~4,3 GB) y la configuración de pgAdmin y RedisInsight. Usalo sólo para empezar de cero y luego repetí el camino rápido.

**Si ya tenías esta práctica levantada de una versión anterior,** el volumen de PostgreSQL no tiene el rol `replicator` ni la extensión `pg_stat_statements`, porque los scripts de `postgres/init/` corren sólo al crear el volumen. Lo más simple es recrear todo con `down -v` (perdés los datos, respaldos y el modelo; repetí el camino rápido). Si preferís conservarlos, aplicá una vez los dos scripts (el segundo requiere que el servicio se haya recreado con `up -d postgres`):

```bash
docker compose --env-file .env -f compose.yaml up -d postgres
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/08-monitoring.sql'
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/09-replication.sql'
```

## Mapa de archivos

| Ruta | Responsabilidad |
| --- | --- |
| [`compose.yaml`](compose.yaml) | Servicios (primario, réplica opcional, Redis con ACL, SeaweedFS, pgAdmin, RedisInsight), salud, volúmenes y límites de recursos |
| [`api/`](api/) | FastAPI, UI con selector de usuario y flujos RAG / SQL / integrado |
| [`loader/`](loader/) | Proyección a Redis por organización y servicio de carga `uploader` |
| [`shared/`](shared/) | Usuarios y tenants, embeddings, recuperación pgvector, esquema por tenant y guarda de SQL |
| [`postgres/init/`](postgres/init/) | Extensiones, esquema multi-tenant, roles, RLS (`07-tenant-rls.sql`), monitoreo y replicación |
| [`postgres/pg_hba.conf`](postgres/pg_hba.conf) | Reglas de autenticación, con la regla de replicación del rol `replicator` |
| [`postgres/seed/01-iot.sql`](postgres/seed/01-iot.sql) | Dos organizaciones con sus ubicaciones, dispositivos y mediciones |
| [`postgres/examples/`](postgres/examples/) | Ejemplos SQL y de respaldo: roles, RLS, concurrencia, backup, monitoreo, particionamiento, replicación y los de la Clase 6 |
| [`examples/`](examples/) | Redis por organización (`03`), replicación y failover (`07`), escalabilidad (`08`) |
| [`tests/`](tests/) | Tests con OpenRouter simulado |

Para correr los tests (reconstruí la imagen si cambiaste el código: `docker compose --env-file .env -f compose.yaml build loader`):

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint pytest loader -q
```

## Problemas frecuentes

- **`port is already allocated`:** algún puerto (8007, 5057, 5541, 5437, 5438, 6380, 18334, 18889, 19334) está ocupado; liberalo o cambialo en `.env`. Los puertos difieren de la Clase 6 (8006, 5056, 5540, 5436, 6379…) para que convivan, aunque con ambas levantadas el consumo de memoria es alto. La Clase 5 todavía usa Redis en 6379 y RedisInsight en 5540: no chocan, pero conviene detenerla.
- **pgAdmin no conecta:** usá el host `postgres` (o `postgres-replica`) y el puerto `5432`, no `localhost`. Si cambiaste el email o la contraseña en `.env` después del primer arranque no se aplican: `down` y `docker volume rm ceiot-clase-07_pgadmin_data`.
- **Las consultas devuelven 0 filas o Redis no tiene claves:** falta el seed (paso 3) o expiró el TTL; repetí los pasos 3 y 4. Con `app_iot`, `ai_readonly` o `rag_readonly` y **sin tenant** también ves 0 filas: es RLS fallando cerrada, no un error.
- **Ves datos de las dos organizaciones en pgAdmin:** estás conectado como `ceiot`, que ignora RLS. Es lo esperado.
- **La primera indexación tarda:** se descarga `BAAI/bge-m3` (~4,3 GB). Esperá y repetí la carga si se cortó.
- **`/api/query` dice que falta la clave o revisá modelo, saldo y conectividad:** completá `OPENROUTER_API_KEY` en `.env`, verificá saldo y conectividad, y recreá `app`. No imprimas ni pegues la clave al pedir ayuda.
- **`422` en `/api/query`:** falta `user_id` o es desconocido (`ana`, `bruno`), o enviaste un campo extra como `tenant_id`.
- **Carga con `422`, `413`, `429` o `503`:** PDF inválido, cifrado o sin texto; más de 50 MiB; otra carga en curso; o un servicio caído (`docker compose --env-file .env -f compose.yaml ps`).
- **La réplica no aparece o no es `streaming`:** levantala con `--profile replica` y esperá a que termine el clon inicial (`logs postgres-replica`). Si quedó a medias, `sh examples/07-failover.sh reset` la recrea.
- **El script de concurrencia no avanza:** las pausas son `\prompt` de `psql`, no funcionan en pgAdmin ni con `exec -T`. Si dejaste una transacción abierta, cerrá la terminal y restaurá el valor como dueño.
- **El disco crece con la réplica caída:** el slot `replica_1` retiene WAL; `max_slot_wal_keep_size=1GB` lo acota. Para soltarlo, levantá la réplica o hacé `reset`.

## Lista de comprobación

- [ ] Los servicios quedan saludables y `/health` responde `ok` en el puerto 8007.
- [ ] pgAdmin conecta con el host `postgres` y abre los scripts desde `examples` y `seed`.
- [ ] El seed informa `organization_count` 2 y estas organizaciones: A con 3 / 4 / 104 y B con 1 / 2 / 144 (ubicaciones / dispositivos / mediciones, "o más").
- [ ] El `loader` imprime 5 claves `iot:org-N:last-known:*` con TTL 3600.
- [ ] `01-roles-permisos.sql` muestra `Rechazado:` en el `DELETE`, el `CREATE TABLE` y el `UPDATE` de `model`.
- [ ] `02-rls.sql`: sin contexto 0 filas, tenant 1 ve 4 equipos, tenant 2 ve 2, el `INSERT` cruzado es rechazado y el dueño ve todo.
- [ ] Como Ana y como Bruno, Text-to-SQL devuelve sólo datos de su organización y `/api/sql-schema?user_id=…` difiere entre ambos; un `tenant_id` enviado por el cliente da `422`.
- [ ] Un PDF subido por Ana no aparece para Bruno (`404` por API) y Bruno recibe "No encontré evidencia…" sin llamar a OpenRouter.
- [ ] `03-redis.sh` muestra el `GET` permitido y dos `NOPERM` para `tenant_1`.
- [ ] Concurrencia: valores finales 120 (perdida), 40 (`FOR UPDATE`), 90 (`REPEATABLE READ`) y un `deadlock detected`.
- [ ] Backup: los conteos coinciden, hay 6 políticas RLS restauradas y `recuperar` devuelve las mediciones de `PLT-002`.
- [ ] Monitoreo: `pg_stat_statements` lista consultas y `VACUUM` deja `n_dead_tup` en 0.
- [ ] Particionamiento: el plan de un mes toca una sola partición y `DETACH`+`DROP` es mucho más rápido que el `DELETE`.
- [ ] Replicación: `state = streaming`, la escritura en la réplica falla y, tras borrar `PLT-002`, la réplica también lo pierde hasta recuperar el dump.
- [ ] Escalabilidad: con 1 CPU los tps bajan respecto de 2 CPU y primario + réplica superan al primario solo.
