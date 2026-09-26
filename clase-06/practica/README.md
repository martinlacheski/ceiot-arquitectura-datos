# Práctica autónoma de especialización e IA sobre datos IoT

Esta práctica conecta TimescaleDB, PostGIS, Redis, SeaweedFS S3, carga de PDF, embeddings E5, pgvector, RAG y Text-to-SQL en un caso pequeño con dos dispositivos protagonistas: el sensor ambiental `AMB-001` (modelo `ENV-X`) en el **Aula 204**, cuyo manual describe la recalibración tras reemplazar la batería, y el sensor de calidad de aire `AIR-002` en el Laboratorio 101. Un tercer dispositivo `ENV-X` (`AMB-005`) vive en Ciudad Universitaria, a unos 10 km, y sirve para probar proximidad geográfica. Todo el recorrido está resuelto y es no evaluativo. Primero ejecutá el camino rápido; después observá cada tecnología de forma nativa con el ritmo **comando → observable esperado → interpretación → variación segura → recuperación**.

PostgreSQL conserva la verdad base; Redis mantiene una proyección temporal del último estado; SeaweedFS conserva tanto el manual inicial como cada PDF cargado; pgvector indexa fragmentos derivados para recuperarlos por similitud. La aplicación pública consulta con `ai_readonly` y `rag_readonly`: no recibe credenciales de escritura. Sólo conserva la clave de OpenRouter para una consulta posterior. La escritura queda aislada en el servicio interno no publicado `uploader`, que usa exclusivamente `rag_ingest`, no recibe la clave de OpenRouter ni credenciales de propietario y está limitado a 2 GiB, 2 CPU y 256 procesos.

## Camino rápido

Todos los comandos parten del directorio de la práctica:

```bash
cd clase-06/practica
```

1. Creá la configuración local sin sobrescribir una existente:

   ```bash
   test -e .env || cp .env.example .env
   ```

   La clave de OpenRouter pertenece únicamente a la variable `OPENROUTER_API_KEY` de tu archivo local `.env`. No escribas el valor en documentación, comandos, capturas ni archivos versionados. `.gitignore` excluye `.env` y sus variantes locales; la plantilla pública se conserva como excepción.

2. Levantá y esperá los servicios:

   ```bash
   docker compose --env-file .env -f compose.yaml up -d --build --wait
   ```

3. Sobre un volumen existente creado antes de esta alineación, aplicá primero la evolución idempotente que agrega ubicaciones geográficas (podés repetirla sin riesgo; también corre sola en un volumen fresco):

   ```bash
   docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/init/06-locations.sql
   ```

4. Cargá las ubicaciones, los dispositivos y el historial de mediciones:

   ```bash
   docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/seed/01-iot.sql
   ```

   El resultado final debe mostrar `location_count=3`, `device_count=4`, `manual_count=1` y `measurement_count` igual o mayor a `104` (8 mediciones fijas del 2025-05-12 más 96 horas recientes de `ENV-X`) en un volumen fresco, antes de cargar otros PDF. Repetir el seed en una hora distinta agrega mediciones nuevas: el conteo crece con cada resiembra tardía y no vuelve a 104. Después de una carga de PDF, el recuento de documentos también crece; no esperes que vuelva a uno.

5. Generá el PDF de dos páginas, subilo a S3 y proyectá el último estado a Redis:

   ```bash
   docker compose --env-file .env -f compose.yaml run --rm loader
   ```

   La salida confirma el bucket y la clave, `PDF=2 páginas`, una huella SHA-256 y un TTL de Redis cercano a `3600s`.

6. Descargá E5 la primera vez e indexá los cuatro fragmentos:

   ```bash
   docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader -m loader.ingest_vectors
   ```

   La salida esperada termina con `Indexación completa: 4 chunks de env-x-manual v1`.

7. Abrí [http://127.0.0.1:8006/](http://127.0.0.1:8006/) o verificá primero la API:

   ```bash
   curl --fail http://127.0.0.1:8006/health
   ```

   Debe responder `{"status":"ok"}`. La salud de la API no prueba la clave, no carga E5 y no llama a OpenRouter.

> **Dependencias cronológicas:** PostgreSQL debe estar saludable antes del seed; el loader necesita ese seed para construir Redis y necesita SeaweedFS para publicar el PDF; la indexación E5 necesita que el loader haya dejado el manual como `available`; RAG necesita los chunks; Text-to-SQL necesita el seed. Text-to-SQL e integrado necesitan una clave local válida. RAG la necesita únicamente cuando recupera evidencia y debe generar una respuesta; sin fragmentos relevantes devuelve una respuesta determinista sin llamar a OpenRouter.

## Antes de usar IA en vivo

OpenRouter es un proveedor externo. Cada llamada puede tener costo y envía al proveedor la pregunta y el contexto preparado por el flujo. No uses datos personales, secretos ni telemetría sensible. Revisá el modelo y el saldo de tu cuenta antes de la primera llamada. Este laboratorio no reintenta automáticamente una solicitud paga y limita cada respuesta a 300 tokens como máximo.

El smoke en vivo se observó sólo con los prompts documentados más abajo y el modelo configurado en ese momento. Los tests de seguridad usan un cliente simulado. **No existe garantía de que todo prompt funcione:** un modelo puede generar SQL rechazado, interpretar mal una pregunta o inventar una afirmación no respaldada. Siempre inspeccioná el SQL validado, las filas, los extractos de fuente y la traza; no confíes solamente en la prosa generada.

## Mapa de arquitectura

```text
navegador / curl
       │
       ▼
app/ FastAPI + UI ── OpenRouter (sólo al preguntar con IA)
   │          │
   │          ├── shared/sql_guard.py + shared/sql_query.py
   │          │       └── lab_read.* como ai_readonly
   │          ├── catálogo + shared/retrieval.py
   │          │       └── documentos/chunks como rag_readonly
   │          └── proxy de bytes PDF ──► uploader:8007 (sólo red interna)
   │                                      ├── valida y fragmenta
   │                                      ├── E5 passage: en CPU
   │                                      ├── original → SeaweedFS S3
   │                                      └── metadatos/vectores → PostgreSQL como rag_ingest
   ▼
PostgreSQL 17
  ├── TimescaleDB: historial temporal, fuente de verdad
  ├── PostGIS: ubicación y distancia
  └── pgvector: índice derivado de todos los documentos

loader/
  ├── data/manual-content.json → PDF inicial → SeaweedFS S3
  ├── PostgreSQL → última lectura → Redis con TTL
  └── PDF inicial desde S3 → E5 local → pgvector
```

| Componente | Responsabilidad |
| --- | --- |
| [`compose.yaml`](compose.yaml) | Servicios, salud, red local, volúmenes y roles de la demo |
| [`Dockerfile`](Dockerfile) | Una imagen Python CPU compartida por `loader` y `app` |
| [`api/`](api/) | FastAPI, proxy público de carga sin credenciales de escritura, catálogo, cliente OpenRouter, flujos RAG/SQL/integrado y HTML mínimo |
| [`loader/`](loader/) | Creación y verificación del PDF inicial, proyección Redis, ingestión vectorial y servicio interno `uploader` |
| [`shared/`](shared/) | E5, recuperación pgvector, validación SQL y ejecución restringida |
| [`postgres/init/`](postgres/init/) | Extensiones, tablas, roles y vistas de sólo lectura |
| [`postgres/seed/01-iot.sql`](postgres/seed/01-iot.sql) | Tres dispositivos, ocho mediciones y registro versionado del manual |
| [`postgres/examples/`](postgres/examples/) | Consultas nativas temporales, espaciales y vectoriales |
| [`data/manual-content.json`](data/manual-content.json) | Fuente versionada que el loader convierte en un PDF de dos páginas |
| [`tests/`](tests/) | Seguridad SQL, recuperación, proveniencia y API con OpenRouter simulado |

## Requisitos, recursos y tiempo

| Requisito o recurso | Referencia para esta práctica |
| --- | --- |
| Herramientas | Docker con Docker Compose v2 (`docker compose`) y `curl` |
| Imagen compartida | CPU-only; tamaño observado aproximado de **1,94 GB** |
| Disco para Docker | Recomendación estimada: alrededor de **6 GB libres** para imágenes, volúmenes y caché; no es un mínimo verificado |
| Memoria | Recomendación estimada: alrededor de **6 GB de RAM disponibles**; no es un mínimo verificado |
| Primera indexación | Descarga `intfloat/multilingual-e5-small`; el tiempo depende de la red y luego se reutiliza `embedding_model_cache` |
| Acceso externo | E5 necesita Internet sólo para su primera descarga; OpenRouter se usa únicamente en consultas de IA en vivo |

El loader y la API comparten la misma imagen CPU y la misma caché del modelo. Si Docker dispone de menos recursos, el arranque o la primera carga pueden tardar más; estas cifras orientan la preparación del laboratorio y no garantizan rendimiento.

## Puertos, recursos y límites locales

| Servicio | Dirección del host | Uso |
| --- | --- | --- |
| PostgreSQL | `127.0.0.1:5436` | TimescaleDB, PostGIS y pgvector |
| Redis | `127.0.0.1:6379` | Proyección temporal del último estado |
| SeaweedFS S3 | `127.0.0.1:18333` | Manual inicial y originales cargados bajo `uploads/` |
| Aplicación | `127.0.0.1:8006` | UI, catálogo, proxy de carga, `/health` y `/api/query` |
| `uploader` | sin puerto publicado (`8007` interno) | Validación, E5, S3 e ingesta con `rag_ingest` |

Los enlaces son locales. SeaweedFS usa un solo nodo sin TLS ni autenticación S3; los roles `ai_readonly`, `rag_readonly` y `rag_ingest` y sus credenciales fijas son **sólo para esta demo aislada**. `rag_ingest` puede modificar únicamente las tablas de documentos y chunks; no tiene acceso de propietario, a `lab_read` ni a la telemetría. No reutilices esta topología ni esas credenciales en producción.

Si un puerto ya está ocupado, detené el proceso o el laboratorio que lo usa antes de continuar. No cambies otros contenedores para acomodar esta práctica. PostgreSQL, Redis y SeaweedFS permiten cambiar sus puertos publicados mediante `POSTGRES_PORT`, `REDIS_PORT` y `SEAWEEDFS_S3_PORT`; la aplicación queda fijada en `8006`.

## 1. TimescaleDB — historial y agregación temporal

### Comando

```bash
docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/examples/01-temporal.sql
```

### Observable esperado

- `measurements` aparece como hypertable con una dimensión temporal.
- Sobre el día fijo 2025-05-12 hay `8` mediciones y `5` pertenecen a `AIR-002`.
- `time_bucket('1 minute', ...)` devuelve dos minutos para CO₂: `802.5 ppm` a las 10:31 y `812.0 ppm` a las 10:32.
- "¿Cuál fue la temperatura promedio del Aula 204 durante las últimas 24 horas?" (filmina Clase 6) siempre devuelve una fila con promedio y `sample_count`, porque el seed ancla 48 horas de temperatura de `ENV-X` (`AMB-001`) a la hora de ejecución. El desglose horario muestra `has_suspect_reading=true` en las últimas horas por la anomalía sembrada.

### Interpretación

TimescaleDB particiona el historial por `measured_at` sin quitarle a PostgreSQL sus restricciones ni SQL. El promedio de 10:31 usa `799` y `806`; el de 10:32 usa la única lectura `812`. La consulta de Aula 204 recorre `locations -> devices -> measurements`, tal como piden las notas de la filmina, y no depende de una fecha fija: `now() - interval '24 hours'` siempre encuentra datos porque el seed reancla el historial reciente cada vez que se ejecuta.

### Variación segura

Repetí sólo el `SELECT` de agregación fija con un rango final exclusivo `10:32:00Z`. Vas a conservar el bucket de 10:31 y excluir el de 10:32. No cambies el seed.

### Recuperación

La variación es de sólo lectura. Volvé a ejecutar el archivo completo para recuperar la observación canónica.

## 2. PostGIS — proximidad sobre geografía

### Comando

```bash
docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/examples/02-spatial.sql
```

### Observable esperado

`ST_DWithin(..., 30)` desde `AIR-002` devuelve exactamente:

- `AIR-002`, a `0.0 m`;
- `AMB-001`, a aproximadamente `20 m`.

`ACT-003`, a unos 60 m, queda fuera. La consulta siguiente confirma un índice GiST llamado `devices_position_gix`.

"¿Qué dispositivos se encuentran a menos de 2 km de esta ubicación?" (filmina Clase 6), usando un punto arbitrario cercano al Aula 204, devuelve `AIR-002`, `AMB-001` (`ENV-X`) y `ACT-003`, los tres a menos de 100 m. `AMB-005` (`ENV-X` en Ciudad Universitaria, a unos 10 km) queda excluido. La última consulta confirma el índice GiST `locations_position_gix`.

### Interpretación

La columna es `geography(Point, 4326)`, por lo que el radio y `ST_Distance` se expresan en metros. `ST_DWithin` formula el filtro espacial y el índice GiST permite evitar una comparación exhaustiva cuando el corpus crece. Las ubicaciones (`locations`) son una entidad propia: varios dispositivos pueden compartir aula y un dispositivo lejano (`AMB-005`) sirve para demostrar que el filtro de proximidad realmente excluye.

### Variación segura

Copiá el primer `SELECT` y reducí el radio de `30` a `10`: sólo debe quedar `AIR-002`. Para la consulta de 2 km, reducí el radio a `100`: seguís obteniendo los tres dispositivos cercanos al Aula 204.

### Recuperación

No hubo escrituras. Restaurá el radio `30` o ejecutá nuevamente el archivo.

## 3. Redis — último estado reconstruible

### Comando

Ejecutalo después del loader y antes de que expire la clave canónica:

```bash
sh examples/03-redis.sh
```

### Observable esperado

La clave `iot:last-known:AIR-002` contiene `source_of_truth=postgres.measurements`, las últimas lecturas de CO₂ `812`, humedad `47.8` y temperatura `24.6`, y un TTL positivo de hasta `3600` segundos. El script crea además `iot:last-known:AIR-002:practice` con TTL `20`, la lee y la elimina.

### Interpretación

Redis acelera la lectura del estado actual, pero no reemplaza el historial. Su clave puede expirar o perderse; PostgreSQL sigue siendo la fuente de verdad desde la cual se reconstruye.

### Variación segura

El propio script usa únicamente la clave descartable `:practice`; podés volver a ejecutarlo para observar cómo el TTL disminuye. No modifica la clave canónica.

### Recuperación

El script elimina la clave temporal. Si la clave canónica expiró, reconstruíla desde PostgreSQL repitiendo sólo el loader:

```bash
docker compose --env-file .env -f compose.yaml run --rm loader
```

## 4. SeaweedFS S3 — documento original y proveniencia

### Comando de carga

```bash
docker compose --env-file .env -f compose.yaml run --rm loader
```

El loader genera un PDF real de dos páginas desde la fuente versionada, lo sube a `s3://ceiot-manuales/manuales/env-x/v1/manual_ENV_X.pdf`, verifica `HEAD`, descarga con `GET`, compara los bytes y recién entonces marca el documento como disponible.

### Comando nativo de verificación

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader - <<'PY'
import hashlib
import os
import boto3
from botocore import UNSIGNED
from botocore.config import Config

client = boto3.client(
    "s3",
    endpoint_url=os.environ["SEAWEEDFS_S3_ENDPOINT"],
    region_name="us-east-1",
    config=Config(signature_version=UNSIGNED),
)
bucket = os.environ["MANUAL_BUCKET"]
key = "manuales/env-x/v1/manual_ENV_X.pdf"
head = client.head_object(Bucket=bucket, Key=key)
response = client.get_object(Bucket=bucket, Key=key)
try:
    body = response["Body"].read()
finally:
    response["Body"].close()
print({
    "bucket": bucket,
    "key": key,
    "content_type": head["ContentType"],
    "pages": head["Metadata"]["pages"],
    "version": head["Metadata"]["version"],
    "sha256_matches": hashlib.sha256(body).hexdigest() == head["Metadata"]["sha256"],
})
PY
```

### Observable esperado

La salida identifica bucket y clave, `content_type: application/pdf`, `pages: 2`, `version: 1` y `sha256_matches: True`.

### Interpretación

S3 conserva el objeto original; PostgreSQL conserva su identidad, versión, clave y estado. El manual inicial mantiene su clave versionada y cada carga usa `uploads/<document_id>/v1/<sha256>.pdf`. El identificador inmutable es `upload-` seguido por los primeros 24 caracteres del SHA-256 de los bytes: los vectores no sustituyen al documento y cada chunk puede volver a su objeto.

### Variación segura

Repetí sólo `HEAD` y `GET`; son lecturas. No edites el PDF generado ni ningún PDF original de la materia. La sección de carga muestra cómo verificar también un objeto bajo `uploads/` sin imprimir su contenido.

### Recuperación

Si falta el objeto o no coincide su hash, repetí el loader para reconstruir **esta clave versionada** desde `data/manual-content.json`. No cambies otros objetos ni otros contenedores.

## 5. E5 local — fragmentos y prefijos

### Comando

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader -m loader.ingest_vectors
```

### Observable esperado

Se indexan exactamente cuatro chunks:

| Página | Sección |
| --- | --- |
| 1 | Preparación y condiciones |
| 1 | Recalibración tras reemplazo de batería |
| 2 | Comprobación |
| 2 | Recuperación segura |

Cada fila conserva `document_id`, versión `1`, página, sección, `chunk_index`, `object_key`, hash del contenido, modelo y un vector de **384 dimensiones**.

### Interpretación

E5 no usa el mismo texto de entrada para ambos lados: cada fragmento se codifica como `passage: ...` y cada pregunta como `query: ...`. Mezclar u omitir esos prefijos degrada la comparación. El modelo corre en CPU y los embeddings son un índice derivado, no evidencia independiente.

### Variación segura

Volvé a ejecutar la indexación del manual inicial. El `UPSERT` conserva sus cuatro identidades versionadas y actualiza el embedding sin duplicarlas. Una carga repetida con exactamente los mismos bytes conserva el mismo `document_id`, objeto, chunks y título ya almacenado; no crea una copia ni reemplaza el título.

### Recuperación

Si la descarga inicial se interrumpió, comprobá conectividad y espacio de Docker y repetí el mismo comando. No hace falta reiniciar volúmenes.

## 6. pgvector — similitud frente a coincidencia literal

### Comando CLI reproducible

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader -m loader.query_vectors \
  --question '¿Cómo debe recalibrarse el sensor ENV-X después de reemplazar la batería?' \
  --top-k 3
```

### Observable esperado

Sobre el corpus original de cuatro chunks, la búsqueda semántica devuelve `3` vecinos con distancia coseno y la coincidencia de la paráfrasis completa mediante `ILIKE` devuelve `0`. Si ya cargaste documentos, vecinos y orden pueden cambiar. Para observar el operador de PostgreSQL directamente:

```bash
docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/examples/04-vector.sql
```

Ese archivo ordena con `<=>` y muestra la proveniencia junto a cada vecino; después contrasta la misma paráfrasis con `ILIKE`.

### Interpretación

`embedding <=> query_embedding` calcula distancia coseno: menor significa más cercano. La API admite sólo vecinos con distancia `<= 0.20` **antes** de aplicar `top_k`. Ese corte es aproximado y fue calibrado para los cuatro fragmentos iniciales; puede aceptar falsos positivos, rechazar material útil y no promete pertinencia universal para PDF cargados.

### Variación segura

Probá otra pregunta manteniendo `--top-k` entre `1` y `4`. Compará siempre sección, extracto y distancia; una cercanía numérica no vuelve verdadera una respuesta.

### Recuperación

Las consultas no escriben. Si no hay chunks, ejecutá primero el loader y luego la indexación E5, en ese orden.

## 7. RAG — responder desde el manual

### Comando sugerido

Esta es la pregunta de la filmina de la Clase 6; no fue re-verificada en vivo contra OpenRouter después de esta alineación (no se hacen llamadas pagas como parte de esta tarea), por lo que no extrapoles una redacción de respuesta exacta:

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

### Observable esperado

El invariante verificado (por los tests automatizados con un cliente OpenRouter simulado, ver `tests/test_retrieval.py` y `tests/test_web_app.py`) es que la recuperación semántica encuentra **página 1, sección "Recalibración tras reemplazo de batería"** como fragmento más cercano y que la respuesta cita página y sección de ese fragmento. Una ejecución en vivo real depende del modelo configurado y de su redacción, que no está prometida.

### Interpretación

E5 y pgvector recuperan evidencia antes de llamar al proveedor. El modelo recibe contexto, pero puede interpretarlo mal; que un fragmento figure en `sources` no prueba que cada frase lo haya citado correctamente.

### Variación segura: evidencia ausente

Esta pregunta negativa exacta fue verificada de forma independiente **contra el corpus inicial**, antes de cargar otros PDF:

```bash
curl --fail-with-body http://127.0.0.1:8006/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "rag",
    "question": "¿Cuál es el precio de una bicicleta y cómo estará el clima mañana?",
    "top_k": 4,
    "document_id": "env-x-manual"
  }'
```

El resultado determinista esperado es `No encontré evidencia suficiente en el manual para responder.`, con cero fuentes, traza `recuperación-pgvector-sin-resultados` y **sin llamada a OpenRouter**. El filtro explícito evita que un PDF cargado por vos cambie esta observación. Esto está probado para esa redacción exacta: como el corte `0.20` es aproximado y específico del corpus inicial, otras preguntas irrelevantes podrían atravesarlo como falsos positivos.

### Recuperación

Si una pregunta relevante no recupera fuentes, verificá primero los cuatro chunks con el CLI nativo. No reduzcas el corte para forzar una respuesta ni edites el manual original.

## 8. Text-to-SQL — generación bajo una frontera estricta

### Comando observado en vivo

```bash
curl --fail-with-body http://127.0.0.1:8006/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "text-to-sql",
    "question": "¿Cuál fue la temperatura promedio del Aula 204 durante las últimas 24 horas?",
    "top_k": 4
  }'
```

### Observable esperado

El invariante verificado por los tests (con un cliente OpenRouter simulado) es un único `SELECT` validado sobre `lab_read.measurements` filtrando `location_id = 'AULA-204'` y `measured_at >= now() - INTERVAL '24 hours'`, ejecutado como `ai_readonly`. Cuando la consulta devuelve filas con datos, el flujo hace una segunda llamada a OpenRouter para redactar la respuesta en lenguaje natural (por ejemplo "La temperatura promedio fue de 24,7 °C") **usando únicamente esas filas**; ese paso se ve en la traza como `openrouter-respuesta`. Sin datos útiles, la respuesta es el mensaje determinista de siempre y no hay segunda llamada. Esto no fue re-verificado con una llamada real al proveedor como parte de esta tarea (no se hacen llamadas pagas); revisá siempre el SQL y las filas, no sólo la prosa.

### Frontera de seguridad

Antes de ejecutar, SQLGlot exige:

- exactamente un `SELECT` directo;
- una sola vista: `lab_read.measurements`, `lab_read.devices` o `lab_read.locations`;
- sin `JOIN`, CTE, subconsultas, comentarios, catálogos ni funciones ajenas a `AVG`, `COUNT`, `MIN`, `MAX` y `SUM`;
- una única forma de tiempo relativo, `now() - INTERVAL '<n> hours|days|minutes'`, con el literal del intervalo como un entero de hasta 3 dígitos; ninguna otra combinación de `now()`, `INTERVAL` u otras funciones de fecha;
- `LIMIT` literal entre `1` y `50`;
- columnas expuestas por la vista.

Después vuelve a validar y ejecuta con el rol separado `ai_readonly`, `BEGIN READ ONLY`, `statement_timeout`, `lock_timeout`, máximo 50 filas y máximo 64 KiB. El rol no puede leer las tablas del manual, escribir en las tablas base ni crear objetos temporales. `rag_readonly` es otro rol: puede leer sólo documentos/chunks y no las vistas de telemetría.

### Variación segura

Preguntá por `temperature` o por un conteo, o por otra ubicación (`LAB-101`). Si el modelo usa `CO2` en vez de `co2`, produce SQL fuera del período o no devuelve datos útiles, la UI conserva SQL y filas para que puedas diagnosticarlo; no transforma una ausencia en un éxito.

También podés comprobar el guard sin conectarte a PostgreSQL ni ejecutar una escritura:

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint python loader - <<'PY'
from shared.sql_guard import SQLRejected, validate_sql

try:
    validate_sql("DELETE FROM public.measurements")
except SQLRejected as error:
    print(error)
else:
    raise SystemExit("ERROR: el guard aceptó una escritura")
PY
```

La salida comienza con `Consulta rechazada:`. `validate_sql` analiza el texto y lanza `SQLRejected` antes de abrir una conexión o ejecutar SQL, por lo que este ejemplo no modifica la base.

### Recuperación

Una consulta rechazada no se ejecuta. Reformulá la pregunta con dispositivo, variable y fecha explícitos. Nunca copies el SQL generado a una sesión con privilegios de propietario para eludir el guard.

## 9. Consulta integrada — telemetría y manual sin confundir autoridades

### UI

Podés escribir libremente tu pregunta; los ejemplos son opcionales, y la respuesta sigue limitada al manual y a las vistas `lab_read` bajo el guard SQL.

Abrí [http://127.0.0.1:8006/](http://127.0.0.1:8006/), elegí **Integrado**, mantené `top_k=4` y usá este prompt observado en vivo:

```text
¿Cuál fue el promedio de CO2 de AIR-002 el 12 de mayo de 2025 y cómo reinicio de forma segura si falla la comprobación?
```

La misma operación por API es:

```bash
curl --fail-with-body http://127.0.0.1:8006/api/query \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "integrated",
    "question": "¿Cuál fue el promedio de CO2 de AIR-002 el 12 de mayo de 2025 y cómo reinicio de forma segura si falla la comprobación?",
    "top_k": 4,
    "document_id": "env-x-manual"
  }'
```

### Observable esperado

El smoke en vivo devolvió `200`, promedio cercano a `805.6667`, SQL validado con `'co2'`, cuatro fuentes de `env-x-manual` —incluida **Recuperación segura**— y una respuesta que indicó reiniciar desde las condiciones iniciales y conservar el historial en PostgreSQL. El `document_id` fija esa proveniencia aunque existan cargas posteriores. La traza hace visibles generación SQL, validación, rol, E5, pgvector y síntesis. Esos SQL, filas, fuentes y pasos son invariantes verificables; la prosa no está prometida.

### Interpretación

El flujo combina dos autoridades distintas: telemetría consultada desde PostgreSQL y procedimientos recuperados del manual versionado. Redis puede aparecer en la explicación como copia temporal, pero no aporta el promedio histórico.

### Variación segura: sin manual

Usá una pregunta de telemetría cuya parte documental quede fuera del corpus. El flujo puede devolver la telemetría validada, pero responde `Sin evidencia manual`, incluye `sin-evidencia-manual` y `sin-openrouter-síntesis`, y no realiza la segunda llamada de síntesis. No inventa una cita para completar la respuesta.

### Recuperación

Si falta evidencia manual para una acción, no la infieras desde la telemetría. Volvé al PDF y a los resultados pgvector; reformulá sólo cuando la información realmente exista.

## 10. Carga e inspección de un PDF propio

La carga es local y no llama a OpenRouter. El original queda en S3; sus metadatos y chunks quedan en PostgreSQL/pgvector. Sólo cuando enviás después una pregunta en modo **RAG** o **Integrado** los extractos recuperados pueden salir hacia OpenRouter. Esa llamada puede tener costo y exponer datos personales, información sensible o instrucciones maliciosas incluidas dentro del PDF (*prompt injection*). Revisá siempre extractos y fuentes: el corte `0.20` no garantiza pertinencia para cualquier documento.

### Comando: recorrido en el navegador

No necesitás un PDF personal. Opcionalmente, generá en `/tmp` un PDF sintético reproducible de una página con ReportLab, que ya está instalado en la imagen del loader. Los bytes se redirigen directamente al archivo y nunca se imprimen en la terminal:

```bash
DEMO_PDF=$(mktemp --suffix=.pdf)
docker compose --env-file .env -f compose.yaml run -T --rm --no-deps --entrypoint python loader -c 'import sys; from reportlab.lib.pagesizes import A4; from reportlab.pdfgen import canvas; pdf = canvas.Canvas(sys.stdout.buffer, pagesize=A4, invariant=1); pdf.setTitle("Safe IoT demo"); pdf.drawString(72, 770, "IoT demo: AIR-002 measures indoor CO2 for safe ventilation decisions."); pdf.drawString(72, 748, "Use validated readings and inspect provenance before acting."); pdf.showPage(); pdf.save()' > "$DEMO_PDF"
printf 'PDF sintético creado en: %s\n' "$DEMO_PDF"
```

1. Abrí [http://127.0.0.1:8006/](http://127.0.0.1:8006/) y, en **Cargar e inspeccionar un PDF**, seleccioná la ruta exacta impresa por el comando, o elegí otro PDF de texto autorizado.
2. Presioná **Cargar PDF** y esperá el progreso `Cargando, fragmentando e indexando…`.
3. Revisá el resumen: `document_id`, título, SHA-256, `object_key`, páginas, chunks, modelo, dimensión y preview de seis componentes.
4. En **Documentos disponibles**, elegí **Inspeccionar**. Recorré metadatos, páginas, `chunk_index`, extractos, hashes, `vector_dims=384` y previews de seis valores.
5. En **Nueva consulta**, elegí **RAG**, seleccioná ese documento, escribí una pregunta libre y recién entonces decidí si querés realizar la llamada remota.

Cuando termines, la limpieza opcional elimina únicamente la ruta temporal exacta que acabás de crear:

```bash
rm -- "$DEMO_PDF"
unset DEMO_PDF
```

### Observable esperado

La traza de una carga exitosa avanza por `pdf_validated`, `chunks_embedded`, `s3_stored`, `s3_verified` y `postgres_indexed`. El identificador toma la forma `upload-<24 hex>` y la clave `uploads/<document_id>/v1/<sha256>.pdf`. El catálogo muestra entre 1 y 20 páginas, entre 1 y 120 chunks, E5 `intfloat/multilingual-e5-small`, dimensión `384` y sólo seis componentes de preview.

### Interpretación

El SHA-256 de los bytes define una identidad inmutable. Cargar otra vez exactamente los mismos bytes produce el mismo ID, objeto, chunks y título persistido: no duplica ni reemplaza el documento. Esta práctica no ofrece borrado ni reemplazo. Admite hasta **10 MiB**, **20 páginas**, **20.000 caracteres extraídos por página** (`MAX_PAGE_CHARS=20000` en el parser), **200.000 caracteres extraídos en total** y **120 chunks**; ambos límites de caracteres se aplican, sólo procesa texto extraíble, no hace OCR y rechaza PDF cifrados.

La aplicación es un proxy: valida el límite y reenvía bytes al `uploader` interno. `app` conserva sólo `ai_readonly`, `rag_readonly` y la clave para consultas posteriores; `uploader` no está publicado, usa `rag_ingest` limitado a las tablas documentales y no recibe OpenRouter ni credenciales de propietario.

### Variación segura: inspección local sin llamada paga

Copiá de la UI tu propio `document_id`; no uses un ID sintético. Esta consulta genera el embedding `query:` en `app`, recupera como `rag_readonly` y muestra sólo proveniencia y distancia, no el texto del PDF:

```bash
read -r -p 'DOC_ID mostrado por la UI: ' DOC_ID
docker compose --env-file .env -f compose.yaml exec -T -e DOC_ID="$DOC_ID" app python - <<'PY'
import os
from shared.e5 import embedding_model, query_text, vector_literal
from shared.rag_connection import rag_connection_settings
from shared.retrieval import nearest_manual_chunks
import psycopg

question = "¿Cuál es la idea principal de este documento?"
vector = vector_literal(embedding_model().encode(query_text(question), normalize_embeddings=True))
with psycopg.connect(**rag_connection_settings()) as connection, connection.cursor() as cursor:
    sources = nearest_manual_chunks(cursor, vector, 4, document_id=os.environ["DOC_ID"])
for source in sources:
    print({
        "document_id": source["document_id"],
        "page": source["page"],
        "chunk_index": source["chunk_index"],
        "object_key": source["object_key"],
        "distance": round(source["cosine_distance"], 6),
    })
PY
unset DOC_ID
```

No aparece `openrouter` en el recorrido. Entre cero y cuatro filas es un resultado válido: menor distancia indica mayor cercanía, no verdad ni pertinencia universal.

Para comprobar de forma acotada el índice PostgreSQL con el mismo rol de sólo lectura:

```bash
read -r -p 'DOC_ID mostrado por la UI: ' DOC_ID
docker compose --env-file .env -f compose.yaml exec -T -e DOC_ID="$DOC_ID" app python - <<'PY'
import os
import psycopg
from shared.rag_connection import rag_connection_settings

with psycopg.connect(**rag_connection_settings()) as connection, connection.cursor() as cursor:
    cursor.execute("""
        SELECT current_user AS role, count(*) AS chunks,
               min(vector_dims(embedding)) AS min_dims,
               max(vector_dims(embedding)) AS max_dims
        FROM public.manual_chunks
        WHERE document_id = %s
    """, (os.environ["DOC_ID"],))
    print(dict(cursor.fetchone()))
PY
unset DOC_ID
```

El observable es `role: rag_readonly`, el recuento del documento y `min_dims=max_dims=384`. Es un `SELECT` filtrado; no imprime embeddings ni contenido.

Por último, verificá `HEAD` y el hash de `GET` desde `uploader`. El script consulta una única clave como `rag_ingest`, usa S3 local sin firma y nunca imprime bytes ni credenciales:

```bash
read -r -p 'DOC_ID mostrado por la UI: ' DOC_ID
docker compose --env-file .env -f compose.yaml exec -T -e DOC_ID="$DOC_ID" uploader python - <<'PY'
import hashlib
import os
from loader.pdf_storage import _postgres_connection, _s3_client

document_id = os.environ["DOC_ID"]
with _postgres_connection() as connection, connection.cursor() as cursor:
    cursor.execute("""
        SELECT current_user, version, object_key, sha256, byte_count,
               page_count, content_type
        FROM public.manual_documents
        WHERE document_id = %s AND storage_status = 'available'
        ORDER BY version DESC LIMIT 1
    """, (document_id,))
    row = cursor.fetchone()
if row is None:
    raise SystemExit("Documento no encontrado")
role, version, key, expected_sha, expected_bytes, page_count, content_type = row
expected_metadata = {
    "sha256": expected_sha,
    "document-id": document_id,
    "version": str(version),
    "pages": str(page_count),
}
client = _s3_client()
head = client.head_object(Bucket=os.environ["MANUAL_BUCKET"], Key=key)
response = client.get_object(Bucket=os.environ["MANUAL_BUCKET"], Key=key)
digest = hashlib.sha256()
try:
    while block := response["Body"].read(1024 * 1024):
        digest.update(block)
finally:
    response["Body"].close()
print({
    "role": role,
    "object_key": key,
    "head_content_type_match": head["ContentType"] == content_type,
    "head_bytes_match": head["ContentLength"] == expected_bytes,
    "head_metadata_match": head["Metadata"] == expected_metadata,
    "get_sha256_match": digest.hexdigest() == expected_sha,
})
PY
unset DOC_ID
```

El resultado esperado informa `role: rag_ingest`, la clave seleccionada y los cuatro controles en `True`. La salida contiene sólo el rol, la clave y booleanos: no expone secretos ni bytes. Aunque ese rol puede ingerir documentos, este comando ejecuta únicamente un `SELECT`, `HEAD` y `GET`.

### Recuperación

- **Archivo inválido o sin texto:** elegí un PDF real con texto extraíble. No renombres una imagen a `.pdf`; exportala con texto o aplicá OCR fuera de este laboratorio y revisá el resultado antes de reintentar.
- **Más de 10 MiB, 20 páginas, 20.000 caracteres extraídos en una página (`MAX_PAGE_CHARS=20000`), 200.000 caracteres extraídos en total o 120 chunks:** generá una copia acotada que conserve sólo las páginas y el texto necesarios y volvé a cargarla. El límite del parser por página es independiente del total: repartí contenido demasiado denso entre páginas cuando corresponda. No reduzcas límites ni reemplaces objetos manualmente.
- **PDF cifrado:** trabajá sobre una copia descifrada autorizada y sin información sensible; el original se rechaza antes de almacenar o indexar.
- **`429` o `503`:** esperá a que termine la única ingesta activa; verificá `docker compose --env-file .env -f compose.yaml ps` y reintentá una vez. No envíes cargas en bucle.
- **Falla después de almacenar:** repetí los mismos bytes cuando PostgreSQL, S3 y `uploader` estén saludables. La identidad por hash converge al mismo documento y no crea otra versión.

### Variación segura: persistencia tras un reinicio

Anotá desde la UI `document_id`, SHA-256, `object_key` y cantidad de chunks. Reiniciá sin borrar volúmenes:

```bash
docker compose --env-file .env -f compose.yaml restart postgres seaweedfs uploader app
```

Esperá servicios saludables, recargá la UI e inspeccioná el mismo documento. Los cuatro valores deben coincidir y la consulta acotada debe conservar `384` dimensiones. Eso prueba persistencia en este volumen; `restart` no prueba una inicialización desde volumen fresco. No ejecutes `down -v` para esta comprobación.

## Verificación automatizada sin llamadas reales

Los tests inyectan respuestas simuladas de OpenRouter y prueban recuperación, SQL hostil, roles restringidos, carga, límites, errores sanitizados, API y UI. No hacen una llamada paga:

```bash
docker compose --env-file .env -f compose.yaml run --rm --entrypoint pytest loader -q
```

La ejecución normal observada termina con **143 aprobados, 1 omitido opcional y 2 warnings de dependencias upstream**. El único test omitido consulta el catálogo del volumen actual en modo de sólo lectura. Para incluirlo explícitamente:

```bash
docker compose --env-file .env -f compose.yaml run --rm \
  -e RUN_LIVE_SEED_CATALOG_CHECK=1 --entrypoint pytest loader -q
```

La ejecución opt-in observada termina con **144 aprobados** y los mismos 2 warnings upstream. El éxito demuestra las fronteras programadas, no la calidad universal de un modelo remoto. No se verificó una inicialización desde volumen fresco y no se ejecutó `down -v`; el smoke real tuvo éxito únicamente para los prompts acotados de esta guía.

## Solución de problemas

| Síntoma | Diagnóstico seguro | Recuperación |
| --- | --- | --- |
| `port is already allocated` | El puerto local 5436, 6379, 18333 u 8006 ya está ocupado. | Detené el proceso conflictivo; no cambies ni borres otros contenedores. |
| PostgreSQL no queda saludable | Las tres extensiones deben existir juntas en la imagen fijada. | Revisá `docker compose --env-file .env -f compose.yaml ps` y los logs de `postgres`; no sustituyas silenciosamente una extensión. |
| Redis devuelve `-2` para TTL | La clave canónica expiró o no fue cargada. | Repetí `run --rm loader`; reconstruye desde PostgreSQL y restaura TTL 3600. |
| No hay chunks | Falta el PDF disponible o la indexación inicial. | Para el manual, ejecutá loader y luego `loader.ingest_vectors`; para una carga, revisá `uploader` y reintentá los mismos bytes. |
| La primera indexación o carga tarda | E5 se está descargando o procesando en CPU dentro del límite del servicio. | Esperá y comprobá conectividad, espacio y salud; no cambies a una imagen GPU ni amplíes límites sin medir. |
| La carga devuelve `422` | El archivo no es PDF válido, está cifrado, no tiene texto extraíble o supera páginas/caracteres/chunks. | Corregí una copia autorizada según el mensaje y reintentá; no fuerces la extensión ni los límites. |
| La carga devuelve `413` | El cuerpo supera 10 MiB, incluso si faltaba `Content-Length`. | Generá una copia de hasta 10 MiB; no la comprimas o trunques de forma que pierda legibilidad. |
| La carga devuelve `429` | Otra ingesta mantiene la compuerta interna. | Esperá a que termine y reintentá una vez; no paralelices cargas. |
| Catálogo o carga devuelve `503` | PostgreSQL, S3 o `uploader` no está disponible; el detalle interno fue sanitizado. | Consultá `compose ps` y logs del servicio afectado sin imprimir variables ni configuración expandida. |
| El mismo PDF conserva el título anterior | La identidad depende de los bytes y la carga duplicada es idempotente. | Es el comportamiento esperado; no hay reemplazo. Cambiá el contenido sólo si realmente es otro documento. |
| `/api/query` responde que falta la clave | La API arrancó correctamente, pero el modo IA está deshabilitado. | Colocá la clave sólo en `OPENROUTER_API_KEY` de tu `.env` local y recreá `app`; no la imprimas para diagnosticar. |
| OpenRouter devuelve error | Puede faltar saldo, conectividad o disponibilidad del modelo. | Revisá esos tres factores en el proveedor sin mostrar la clave; no repitas en un bucle. |
| SQL rechazado o promedio nulo | El modelo generó una forma no admitida, un literal con mayúsculas incorrectas o otro rango. | Inspeccioná SQL/filas y reformulá; no amplíes privilegios. |
| RAG recupera algo irrelevante | El corte `0.20` es corpus-específico y admite falsos positivos. | Leé extractos y distancias; rechazá afirmaciones no respaldadas. |

Para consultar estado sin expandir ni mostrar variables de entorno:

```bash
docker compose --env-file .env -f compose.yaml ps
```

Evitá comandos de configuración expandida y no pegues el contenido de `.env` en pedidos de ayuda.

## Cierre seguro

Detené contenedores y red conservando PostgreSQL, Redis, S3 y la caché del modelo:

```bash
docker compose --env-file .env -f compose.yaml down
```

El reinicio posterior puede usar:

```bash
docker compose --env-file .env -f compose.yaml up -d --build --wait
```

> **Reinicio destructivo — documentado, no ejecutar durante el recorrido:** `docker compose --env-file .env -f compose.yaml down -v` elimina todos los volúmenes nombrados: historial, proyección Redis, objetos S3 y caché E5. Reservalo para una decisión explícita de borrar todo; no es un paso de recuperación normal.

## Lista de comprobación

- [ ] El entorno se creó sin sobrescribir `.env` y los cuatro puertos locales están disponibles.
- [ ] PostgreSQL tiene tres extensiones, tres ubicaciones, cuatro dispositivos, ocho mediciones fijas del 2025-05-12 y una hypertable.
- [ ] Los promedios por minuto son `802.5` y `812.0`; el promedio de temperatura del Aula 204 en las últimas 24 horas siempre devuelve una fila.
- [ ] PostGIS devuelve `AIR-002` a 0 m y `AMB-001` a ~20 m con índice GiST; a 2 km del Aula 204 aparecen los tres dispositivos cercanos y `AMB-005` queda excluido.
- [ ] Redis muestra la proyección con TTL de hasta 3600 s y elimina la clave descartable de 20 s.
- [ ] SeaweedFS conserva el PDF inicial y cada original cargado con bucket, clave, metadatos y hash coincidentes.
- [ ] La aplicación pública sigue limitada a `ai_readonly`/`rag_readonly`; el `uploader` interno usa sólo `rag_ingest`, sin OpenRouter ni rol propietario, con 2 GiB, 2 CPU y 256 procesos.
- [ ] Un PDF de texto válido muestra progreso, identidad SHA inmutable, páginas, chunks, E5 de 384 dimensiones y preview de seis valores.
- [ ] Un PDF inválido, sobredimensionado o cifrado falla de forma explícita y permite un reintento seguro; no hay borrado ni reemplazo.
- [ ] La misma carga conserva ID, objeto, chunks y título; el inventario permite inspeccionar y seleccionar el documento para RAG.
- [ ] E5 usa `passage:` para chunks y `query:` para preguntas; pgvector devuelve tres vecinos sólo sobre el corpus original, donde la paráfrasis literal devuelve cero.
- [ ] La respuesta RAG se contrasta con página, sección y extracto; la ausencia de evidencia evita la llamada remota.
- [ ] El SQL visible es un único `SELECT` admitido, ejecutado como `ai_readonly`, y el promedio es ~`805.6667`.
- [ ] El modo integrado separa telemetría de evidencia manual y no sintetiza cuando falta el manual.
- [ ] La inspección local muestra `rag_readonly`, proveniencia/distancia y `vector_dims=384` sin llamada paga ni contenido PDF crudo.
- [ ] `HEAD`/`GET` desde `uploader` confirma tipo, tamaño, metadatos y hash sin imprimir contenido ni credenciales.
- [ ] Se comprendieron costo, privacidad, prompt injection, posibles errores del modelo y que el corte `0.20` no es universal.
- [ ] Un reinicio conserva identidad y chunks; no se confunde esa prueba con una inicialización en volumen fresco.
- [ ] La suite normal informa 143 aprobados/1 omitido opcional y la opt-in 144 aprobados; ambos casos conservan 2 warnings upstream.
- [ ] El cierre usa `down` sin `-v`.
