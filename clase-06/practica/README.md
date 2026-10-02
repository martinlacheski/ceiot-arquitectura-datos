# Práctica autónoma de especialización e IA sobre datos IoT

Esta práctica conecta TimescaleDB, PostGIS, Redis, SeaweedFS (S3), embeddings locales con `BAAI/bge-m3`, pgvector, RAG, Text-to-SQL y un orquestador en el caso de las filminas de la Clase 6: el sensor ambiental `AMB-001` (modelo `ENV-X`) en el **Aula 204** y su manual, que describe la recalibración tras reemplazar la batería. Todo el recorrido está resuelto y es no evaluativo: primero ejecutá el camino rápido y después explorá cada tecnología con los comandos de la tabla.

PostgreSQL conserva la verdad base; Redis guarda una copia temporal del último estado; SeaweedFS guarda los PDF originales; pgvector indexa fragmentos de esos PDF para buscarlos por similitud.

## Requisitos

- Docker con Docker Compose v2 (`docker compose`) y `curl`.
- Unos **10 GB libres** para Docker: la imagen Python ocupa ~2 GB y el modelo `BAAI/bge-m3` ~4,3 GB (se descarga una sola vez).
- Internet para la primera descarga del modelo y, opcionalmente, una clave de [OpenRouter](https://openrouter.ai/) para los modos con IA.

## Servicios y URLs

Todos los puertos se publican sólo en `127.0.0.1` y se pueden cambiar en `.env` (columna Variable).

| Servicio | URL desde tu máquina | Credenciales (por defecto) | Variable | Para qué |
| --- | --- | --- | --- | --- |
| Aplicación web | [http://127.0.0.1:8006/](http://127.0.0.1:8006/) | — | `APP_PORT` | UI de carga de PDF y consultas RAG / Text-to-SQL / Integrado; API en `/api/query`, salud en `/health` |
| pgAdmin | [http://127.0.0.1:5056/](http://127.0.0.1:5056/) | `student@example.edu` / `class6-local` | `PGADMIN_PORT` | Explorar tablas y ejecutar los scripts SQL |
| PostgreSQL | `postgresql://ceiot:ceiot_local_only@127.0.0.1:5436/ceiot_class6` | `ceiot` / `ceiot_local_only` | `POSTGRES_PORT` | TimescaleDB, PostGIS y pgvector (desde pgAdmin usá el host `postgres` y el puerto `5432`) |
| RedisInsight | [http://127.0.0.1:5540/](http://127.0.0.1:5540/) | — (la conexión `ceiot-clase-06` ya viene configurada) | `REDISINSIGHT_PORT` | Cliente web de Redis: ver claves, valores y TTL |
| Redis | `redis://:ceiot_redis_local_only@127.0.0.1:6379/0` | contraseña `ceiot_redis_local_only` | `REDIS_PORT` | Copia temporal del último estado (`iot:last-known:AIR-002`) |
| SeaweedFS S3 | `http://127.0.0.1:18333` | sin autenticación | `SEAWEEDFS_S3_PORT` | Endpoint S3 para clientes como `aws s3 --endpoint-url` |
| SeaweedFS filer | [http://127.0.0.1:18888/buckets/](http://127.0.0.1:18888/buckets/) | sin autenticación | `SEAWEEDFS_FILER_PORT` | Navegar los buckets y descargar los PDF guardados (`ceiot-manuales/`) |
| SeaweedFS master | [http://127.0.0.1:19333/](http://127.0.0.1:19333/) | sin autenticación | `SEAWEEDFS_MASTER_PORT` | Estado del clúster de un solo nodo y sus volúmenes |

El servicio interno `uploader` (indexa los PDF subidos) no publica puerto: sólo lo usa la aplicación. Las credenciales son **exclusivas de este laboratorio local**; no las reutilices.

## Camino rápido

Todos los comandos parten del directorio de la práctica (`cd clase-06/practica`).

1. Creá la configuración local sin pisar una existente:

   ```bash
   test -e .env || cp .env.example .env
   ```

2. Levantá los servicios y esperá a que estén saludables:

   ```bash
   docker compose --env-file .env -f compose.yaml up -d --build --wait
   ```

   Levanta PostgreSQL, Redis, SeaweedFS, pgAdmin, `uploader` y la aplicación. Comprobá el estado con `docker compose --env-file .env -f compose.yaml ps`: todos deben figurar `healthy`. La base arranca vacía de datos (sólo esquema, roles y vistas).

3. Cargá ubicaciones, dispositivos y mediciones (el script ya está montado en el contenedor en `/lab/seed`):

   ```bash
   docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/seed/01-iot.sql'
   ```

   También podés abrir `seed/01-iot.sql` desde pgAdmin y ejecutarlo (ver [Ejecutar los scripts](#ejecutar-los-scripts)). Al final debe mostrar `location_count=3`, `device_count=4`, `manual_count=1` y `measurement_count` de 104 o más (repetir el seed agrega mediciones recientes).

4. Generá el PDF del manual, subilo a S3 y copiá el último estado a Redis:

   ```bash
   docker compose --env-file .env -f compose.yaml run --rm loader
   ```

   La salida confirma el bucket y la clave, `PDF=2 páginas`, el SHA-256 y el TTL de Redis. El PDF queda visible en [http://127.0.0.1:18888/buckets/ceiot-manuales/](http://127.0.0.1:18888/buckets/ceiot-manuales/).

5. Indexá el manual (la primera vez descarga `BAAI/bge-m3`):

   ```bash
   docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader -m loader.ingest_vectors
   ```

   Debe terminar con `Indexación completa: 4 chunks de env-x-manual v1`.

6. Comprobá la API y abrí la UI en [http://127.0.0.1:8006/](http://127.0.0.1:8006/):

   ```bash
   curl --fail http://127.0.0.1:8006/health
   ```

   Responde `{"status":"ok"}`.

7. (Opcional) Entrá a pgAdmin en [http://127.0.0.1:5056/](http://127.0.0.1:5056/) y registrá el servidor como se explica en [Conectar pgAdmin](#conectar-pgadmin).

> **Orden de los pasos:** el loader necesita el seed (paso 3) para construir Redis, y la indexación necesita el loader (paso 4). RAG necesita los chunks del paso 5; Text-to-SQL necesita el seed.

> **Clave de OpenRouter:** los modos **Text-to-SQL** e **Integrado** la necesitan, y **RAG** cuando encuentra evidencia y debe redactar la respuesta. Escribila sólo en `OPENROUTER_API_KEY` de tu `.env` local (no se versiona) y recreá la app con `up -d --build`. Cada llamada puede tener costo y envía tu pregunta y el contexto al proveedor: no uses datos personales ni sensibles. Revisá siempre el SQL, las filas y las fuentes, no sólo la prosa del modelo.

## Conectar pgAdmin

1. Abrí [http://127.0.0.1:5056/](http://127.0.0.1:5056/) e ingresá con `student@example.edu` / `class6-local`.
2. Clic derecho en **Servers → Register → Server...**
3. Pestaña **General**: nombre `Clase 6`.
4. Pestaña **Connection**:

   | Campo | Valor |
   | --- | --- |
   | Host name/address | `postgres` |
   | Port | `5432` |
   | Maintenance database | `ceiot_class6` |
   | Username | `ceiot` |
   | Password | `ceiot_local_only` (podés marcar **Save password**) |

5. Guardá y abrí **Databases → ceiot_class6 → Schemas**: `public` tiene las tablas (`locations`, `devices`, `measurements`, `manual_documents`, `manual_chunks`) Son las mismas tablas que lee Text-to-SQL con el rol `ai_readonly` (sólo lectura). En **Properties → Comment** de cada tabla y columna está la documentación que el sistema le pasa al modelo.

`postgres` es el nombre del servicio dentro de la red de Compose: desde pgAdmin **no** uses `localhost` ni `5436`. Si usás otro cliente desde tu máquina (DBeaver, `psql` local), ahí sí conectá a `127.0.0.1:5436`.

## Ejecutar los scripts

Los scripts están montados como sólo lectura dentro de los contenedores, así no hace falta copiar y pegar:

| Carpeta del repositorio | Dentro de `postgres` y `pgadmin` | Dentro de `redis` |
| --- | --- | --- |
| [`postgres/seed/`](postgres/seed/) | `/lab/seed` | — |
| [`postgres/examples/`](postgres/examples/) | `/lab/examples` | — |
| [`examples/`](examples/) | — | `/lab/examples` |

**Desde pgAdmin:** en el Query Tool usá el ícono de carpeta (**Open File**) y elegí el almacenamiento compartido `examples` o `seed` en el selector del diálogo. Abrí el archivo y ejecutalo con ▶ o F5. Las carpetas son de sólo lectura: si modificás un script, guardalo en tu almacenamiento personal (**My Storage**).

**Desde el contenedor de PostgreSQL**, con `psql`:

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -f /lab/examples/01-temporal.sql'
```

O en forma interactiva, para ejecutar y modificar consultas:

```bash
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
ceiot_class6=# \i /lab/examples/02-spatial.sql
```

**Redis**, dentro del contenedor o desde el host (el script detecta dónde corre):

```bash
docker compose --env-file .env -f compose.yaml exec redis sh /lab/examples/03-redis.sh
sh examples/03-redis.sh
```

**RedisInsight:** abrí [http://127.0.0.1:5540/](http://127.0.0.1:5540/), aceptá los términos de uso la primera vez y entrá a la base `ceiot-clase-06`. En **Browser** buscá `iot:*` para ver la clave `iot:last-known:AIR-002`, su valor JSON y el TTL que baja. Si la lista de bases aparece vacía, agregala a mano con host `redis`, puerto `6379` y la contraseña `ceiot_redis_local_only` (no uses `localhost`: RedisInsight corre en su propio contenedor).

Para explorar Redis desde la terminal abrí `redis-cli` dentro del contenedor (la contraseña se toma de la variable del contenedor y no queda en el historial):

```bash
docker compose --env-file .env -f compose.yaml exec redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli'
127.0.0.1:6379> KEYS iot:*
127.0.0.1:6379> GET iot:last-known:AIR-002
127.0.0.1:6379> TTL iot:last-known:AIR-002
```

**SeaweedFS:** abrí el filer en [http://127.0.0.1:18888/buckets/ceiot-manuales/](http://127.0.0.1:18888/buckets/ceiot-manuales/) para ver el manual inicial (`manuales/env-x/...`) y los PDF subidos desde la UI (`uploads/...`). Si tenés la CLI de AWS, también funciona como S3: `aws s3 ls s3://ceiot-manuales --recursive --endpoint-url http://127.0.0.1:18333 --no-sign-request`.

## Recorrido

| # | Tecnología | Comando o acción | Qué observar |
| --- | --- | --- | --- |
| 1 | TimescaleDB | `postgres/examples/01-temporal.sql` | Hypertable; promedios por minuto de CO₂ `802.5` y `812.0`; temperatura media del Aula 204 en las últimas 24 h (siempre devuelve una fila) |
| 2 | PostGIS | `postgres/examples/02-spatial.sql` | `AIR-002` a 0 m y `AMB-001` a ~20 m; a menos de 2 km del Aula 204 hay tres dispositivos y `AMB-005` (a ~10 km) queda afuera |
| 3 | Redis | `examples/03-redis.sh` (en el contenedor `redis` o desde el host) y RedisInsight | Clave `iot:last-known:AIR-002` con TTL de hasta 3600 s |
| 4 | SeaweedFS | `run --rm loader` (paso 4) y el filer web | Bucket y clave del PDF, `PDF=2 páginas`, SHA-256; el archivo en [`/buckets/ceiot-manuales/`](http://127.0.0.1:18888/buckets/ceiot-manuales/) |
| 5 | bge-m3 | `loader.ingest_vectors` (paso 5) | 4 chunks de 1024 dimensiones |
| 6 | pgvector | `loader.query_vectors` y `postgres/examples/04-vector.sql` | 3 vecinos por similitud; la paráfrasis con `ILIKE` devuelve 0 |
| 7 | RAG | UI o `/api/query` con `"mode": "rag"` | Respuesta con página y sección del manual |
| 8 | Text-to-SQL | UI o `/api/query` con `"mode": "text-to-sql"` | El SQL generado (puede usar `JOIN`, `time_bucket`, PostGIS) y sus filas; el esquema que recibió el modelo en `/api/sql-schema` |
| 9 | Integrado | UI o `/api/query` con `"mode": "integrated"` | Promedio de telemetría + procedimiento del manual |

Los archivos SQL de los pasos 1, 2 y 6 se ejecutan desde pgAdmin o con `psql` dentro del contenedor, como se muestra en [Ejecutar los scripts](#ejecutar-los-scripts).

### Pasos 6 a 9: consultas

Búsqueda por similitud desde la terminal:

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader -m loader.query_vectors \
  --question '¿Cómo debe recalibrarse el sensor ENV-X después de reemplazar la batería?' \
  --top-k 3
```

La distancia coseno menor es más cercana. Sólo se aceptan vecinos con distancia `<= 0.55`.

Las preguntas de las filminas se pueden escribir en la UI (elegí el modo) o enviar por API. Ejemplo RAG:

```bash
curl --fail-with-body http://127.0.0.1:8006/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "rag",
    "question": "¿Cómo debe recalibrarse el sensor ENV-X después de reemplazar la batería?",
    "top_k": 2,
    "document_id": "env-x-manual"
  }'
```

Esperás que el fragmento más cercano sea **página 1, sección "Recalibración tras reemplazo de batería"** y que la respuesta la cite. Con una pregunta sin relación (`¿Cuál es el precio de una bicicleta y cómo estará el clima mañana?`) la respuesta es `No encontré evidencia suficiente en el manual para responder.`, sin fuentes y sin llamar a OpenRouter.

| Pregunta de la filmina | Modo | Resultado esperado |
| --- | --- | --- |
| ¿Cuál fue la temperatura promedio del Aula 204 durante las últimas 24 horas? | `text-to-sql` | Un `SELECT` con `location_id = 'AULA-204'` y `measured_at >= now() - INTERVAL '24 hours'`, y su promedio |
| ¿Cómo debe recalibrarse el sensor ENV-X después de reemplazar la batería? | `rag` | Sección de recalibración del manual |
| El sensor ENV-X del Aula 204 presenta mediciones anómalas. ¿Cuáles fueron sus valores promedio durante las últimas 24 horas y qué procedimiento de calibración indica su manual? | `integrated` | Promedio de la telemetría y procedimiento del manual |

Para Text-to-SQL e Integrado usá el mismo `curl`, cambiando `mode` y `question`. En modo integrado podés agregar `"document_id": "env-x-manual"`. La traza empieza con `orquestador`: una primera llamada separa la pregunta en una parte de telemetría (Text-to-SQL) y otra del manual (RAG), y ejecuta sólo lo necesario.

### Cómo funciona Text-to-SQL (modo abierto)

1. **Descubre el esquema.** Antes de generar SQL, [`shared/sql_schema.py`](shared/sql_schema.py) consulta el catálogo de PostgreSQL con el mismo rol que ejecuta las consultas (`ai_readonly`): tablas, columnas y tipos (`pg_class`, `pg_attribute`), claves primarias y foráneas (`pg_constraint`), comentarios (`COMMENT ON`), extensiones (`pg_extension`) y los valores reales de las columnas de texto con pocos valores distintos (`SELECT DISTINCT`). En el código no hay ningún nombre de tabla escrito: si agregás una tabla y le das `GRANT SELECT` a `ai_readonly`, aparece sola. Mirá lo que recibe el modelo en [http://127.0.0.1:8006/api/sql-schema](http://127.0.0.1:8006/api/sql-schema).
2. **Genera SQL sin reglas artificiales.** El modelo puede usar `JOIN`, subconsultas, CTE, funciones de ventana, `time_bucket` de TimescaleDB y `ST_Distance` de PostGIS.
3. **La base pone los límites.** El SQL se ejecuta como `ai_readonly`: sólo tiene `SELECT` sobre las tablas de `public`, la transacción es `READ ONLY`, hay `statement_timeout` de 1,5 s y se devuelven como máximo 50 filas. El control previo ([`shared/sql_guard.py`](shared/sql_guard.py)) sólo rechaza lo que no es una única consulta de lectura (`INSERT`, `DELETE`, `DROP`, varias sentencias…).
4. **Se corrige una vez.** Si la base rechaza la consulta (columna inexistente, timeout…), el error vuelve al modelo para que la corrija; la traza muestra `reintento-sql`.

Los permisos y comentarios están en [`postgres/init/06-ai-open-access.sql`](postgres/init/06-ai-open-access.sql). En una base creada antes de este cambio aplicalo una vez:

```bash
docker compose --env-file .env -f compose.yaml up -d postgres
docker compose --env-file .env -f compose.yaml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /docker-entrypoint-initdb.d/06-ai-open-access.sql'
```

Preguntas que antes no se podían responder: `¿Qué dispositivos hay en cada ubicación, con el nombre de la ubicación?` (JOIN), `¿Cuál fue la temperatura promedio del Aula 204 por franjas de 6 horas en el último día?` (`time_bucket`), `¿A qué distancia en metros está cada dispositivo del centro de su ubicación?` (PostGIS).

## Subir un PDF desde la UI

1. En [http://127.0.0.1:8006/](http://127.0.0.1:8006/), sección **Cargar e inspeccionar un PDF**, elegí un PDF con texto y presioná **Cargar PDF**.
2. Debajo del botón ves el progreso en vivo (`Indexando fragmento 12 de 93…`).
3. Revisá el resumen (`document_id`, SHA-256, páginas, chunks) y usá **Inspeccionar** en **Documentos disponibles**.
4. En **Nueva consulta** elegí **RAG**, seleccioná el documento y preguntá.

La carga es local y no llama a OpenRouter; sólo la consulta posterior sí lo hace. Tamaño máximo: 50 MiB por defecto (`MAX_PDF_MIB`). Sólo procesa texto: no hace OCR ni acepta PDF cifrados. El tiempo crece con el documento, unos 1,2 s por fragmento (un datasheet de ~90 fragmentos tarda un par de minutos). El mismo archivo subido dos veces no se duplica; no hay borrado.

## Manual en inglés, pregunta en español

La práctica usa `BAAI/bge-m3` porque es multilingüe: permite preguntar en español sobre un manual en inglés. El modelo anterior (`multilingual-e5-small`) tendía a preferir fragmentos en español aunque el correcto estuviera en inglés.

1. Descargá un datasheet oficial, fuera del repositorio:
   - <https://documentation.espressif.com/esp32-wroom-32e_esp32-wroom-32ue_datasheet_en.pdf>
   - <https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf>
   - <https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf>
2. Subilo desde la UI y copiá su `document_id` (`upload-...`).
3. Preguntá en español en modo **RAG** seleccionando ese documento, por ejemplo: `¿Qué corriente mínima debe entregar la fuente de alimentación?` o `¿Qué microcontrolador integra el módulo?`. Esperás que el fragmento más cercano sea la sección en inglés correspondiente (alimentación, descripción del módulo).

Si no recupera lo esperado, verificá que el documento quedó indexado y que elegiste el `document_id` correcto. No subas el corte `0.55` para forzar coincidencias.

## Variables de entorno

Son opcionales y se definen en `.env`; si faltan, rige el valor por defecto. Tras cambiarlas, recreá los servicios con `up -d --build`.

| Variable | Por defecto | Qué controla |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | vacía | Clave para los modos con IA |
| `OPENROUTER_MAX_COMPLETION_TOKENS` | `300` | Tope de tokens de salida por llamada |
| `MAX_PDF_MIB` | `50` | Tamaño máximo de un PDF (MiB) |
| `CHUNK_MAX_CHARS` / `CHUNK_OVERLAP_CHARS` | `1200` / `150` | Tamaño de fragmento y solape (el solape debe ser menor) |
| `EMBEDDING_BATCH_SIZE` | `4` | Fragmentos por lote al calcular embeddings |
| `RAG_MAX_COSINE_DISTANCE` | `0.55` | Distancia máxima aceptada en la recuperación |
| `RAG_MAX_TOP_K` | `4` | Máximo de fragmentos por consulta |
| `REDIS_TTL_SECONDS` | `3600` | Vida de la clave de Redis |
| `MANUAL_BUCKET` | `ceiot-manuales` | Bucket S3 de los manuales |
| `UPLOADER_CPUS` / `UPLOADER_MEM_LIMIT` | `2` / `4g` | Recursos del servicio que indexa PDF |
| `APP_PORT`, `PGADMIN_PORT`, `REDISINSIGHT_PORT`, `POSTGRES_PORT`, `REDIS_PORT` | `8006`, `5056`, `5540`, `5436`, `6379` | Puertos publicados en `127.0.0.1` |
| `SEAWEEDFS_S3_PORT`, `SEAWEEDFS_FILER_PORT`, `SEAWEEDFS_MASTER_PORT` | `18333`, `18888`, `19333` | Puertos de SeaweedFS (S3, filer web y master) en `127.0.0.1` |
| `PGADMIN_DEFAULT_EMAIL` / `PGADMIN_DEFAULT_PASSWORD` | `student@example.edu` / `class6-local` | Acceso a pgAdmin (se aplican al crear el volumen `pgadmin_data`) |

`MODELO_EMBEDDING` (`BAAI/bge-m3`) existe, pero no conviene cambiarlo: el esquema `VECTOR(1024)` y el corte coseno están calibrados para ese modelo.

## Experimentar sin perder el punto de partida

- Las consultas de los pasos 1, 2, 6 y de la UI sólo leen: repetilas y cambiá radios, preguntas o `top_k` libremente.
- El loader, `ingest_vectors` y el seed se pueden repetir; no rompen el estado (el seed suma mediciones recientes).
- Si la clave de Redis expiró, volvé a ejecutar `run --rm loader`.
- Para detener conservando datos y caché del modelo: `docker compose --env-file .env -f compose.yaml down`.
- **`down -v` borra todo** (historial, Redis, PDF, el modelo descargado y la configuración de pgAdmin y RedisInsight). Usalo sólo si querés empezar de cero; luego repetí el camino rápido.

## Mapa de archivos

| Ruta | Responsabilidad |
| --- | --- |
| [`compose.yaml`](compose.yaml) | Servicios (incluidos pgAdmin y RedisInsight), salud, volúmenes, montajes `/lab` y roles de la demo |
| [`api/`](api/) | FastAPI, UI, cliente OpenRouter y flujos RAG / SQL / integrado |
| [`loader/`](loader/) | PDF inicial, proyección a Redis, indexación vectorial y servicio de carga `uploader` |
| [`shared/`](shared/) | Embeddings, recuperación pgvector y validación SQL |
| [`postgres/init/`](postgres/init/) | Extensiones, tablas, roles y vistas de sólo lectura |
| [`postgres/seed/01-iot.sql`](postgres/seed/01-iot.sql) | Dispositivos, mediciones y registro del manual |
| [`postgres/examples/`](postgres/examples/) | Consultas de TimescaleDB, PostGIS y pgvector |
| [`examples/03-redis.sh`](examples/03-redis.sh) | Lectura de la proyección en Redis (host o contenedor) |
| [`data/manual-content.json`](data/manual-content.json) | Contenido del manual ENV-X |
| [`tests/`](tests/) | Tests con OpenRouter simulado: `docker compose --env-file .env -f compose.yaml run --rm --entrypoint pytest loader -q` |

## Problemas frecuentes

- **`port is already allocated`:** algún puerto (8006, 5056, 5540, 5436, 6379, 18333, 18888, 19333) está ocupado; liberalo o cambialo en `.env`. Ojo: la Clase 5 también usa Redis en 6379 y RedisInsight en 5540; detenelas antes (`docker compose down` en su carpeta).
- **pgAdmin no muestra datos o no conecta:** usá el host `postgres` y el puerto `5432`, no `localhost`. Si cambiaste el email o la contraseña en `.env` después del primer arranque, no se aplican: borrá sólo ese volumen con `docker compose --env-file .env -f compose.yaml down` y `docker volume rm ceiot-clase-06_pgadmin_data`.
- **Las consultas devuelven 0 filas o Redis no tiene la clave:** falta el seed (paso 3) o expiró el TTL; repetí los pasos 3 y 4.
- **La primera indexación o carga tarda:** se descarga `BAAI/bge-m3` (~4,3 GB de disco; conviene tener ~10 GB libres). Esperá y repetí el comando si se cortó.
- **`/api/query` dice que falta la clave:** completá `OPENROUTER_API_KEY` en `.env` y recreá `app`. No la imprimas ni la pegues al pedir ayuda.
- **No hay chunks:** ejecutá el loader y luego `loader.ingest_vectors`, en ese orden.
- **Carga con `422`, `413`, `429` o `503`:** PDF inválido, cifrado o sin texto; más de 50 MiB; otra carga en curso; o un servicio caído (`docker compose --env-file .env -f compose.yaml ps`).

## Lista de comprobación

- [ ] Los servicios quedan saludables y `/health` responde `ok`.
- [ ] pgAdmin conecta con el host `postgres` y abre los scripts desde `examples` y `seed`.
- [ ] El seed informa 3 ubicaciones, 4 dispositivos, 1 manual y 104 o más mediciones.
- [ ] TimescaleDB devuelve `802.5` y `812.0` por minuto y el promedio del Aula 204 en 24 h.
- [ ] PostGIS devuelve `AIR-002` y `AMB-001` a 30 m, y excluye `AMB-005` a 2 km.
- [ ] Redis (script o RedisInsight) muestra la clave `iot:last-known:AIR-002` con su TTL.
- [ ] El manual queda indexado en 4 chunks de 1024 dimensiones.
- [ ] pgvector devuelve 3 vecinos donde `ILIKE` devuelve 0.
- [ ] RAG cita la sección de recalibración y sin evidencia no llama a OpenRouter.
- [ ] `/api/sql-schema` muestra el esquema descubierto, Text-to-SQL responde una pregunta con `JOIN` y el modo integrado combina telemetría y manual.
- [ ] Un PDF propio se sube con progreso y un datasheet en inglés responde a una pregunta en español.
