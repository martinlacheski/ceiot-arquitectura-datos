# Práctica autónoma de especialización e IA sobre datos IoT

Esta práctica conecta TimescaleDB, PostGIS, Redis, SeaweedFS (S3), embeddings locales con `BAAI/bge-m3`, pgvector, RAG, Text-to-SQL y un orquestador en el caso de las filminas de la Clase 6: el sensor ambiental `AMB-001` (modelo `ENV-X`) en el **Aula 204** y su manual, que describe la recalibración tras reemplazar la batería. Todo el recorrido está resuelto y es no evaluativo: primero ejecutá el camino rápido y después explorá cada tecnología con los comandos de la tabla.

PostgreSQL conserva la verdad base; Redis guarda una copia temporal del último estado; SeaweedFS guarda los PDF originales; pgvector indexa fragmentos de esos PDF para buscarlos por similitud.

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

3. Cargá ubicaciones, dispositivos y mediciones:

   ```bash
   docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/seed/01-iot.sql
   ```

   Al final debe mostrar `location_count=3`, `device_count=4`, `manual_count=1` y `measurement_count` de 104 o más (repetir el seed agrega mediciones recientes).

4. Generá el PDF del manual, subilo a S3 y copiá el último estado a Redis:

   ```bash
   docker compose --env-file .env -f compose.yaml run --rm loader
   ```

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

> **Clave de OpenRouter:** los modos **Text-to-SQL** e **Integrado** la necesitan, y **RAG** cuando encuentra evidencia y debe redactar la respuesta. Escribila sólo en `OPENROUTER_API_KEY` de tu `.env` local (no se versiona) y recreá la app con `up -d --build`. Cada llamada puede tener costo y envía tu pregunta y el contexto al proveedor: no uses datos personales ni sensibles. Revisá siempre el SQL, las filas y las fuentes, no sólo la prosa del modelo.

## Recorrido

| # | Tecnología | Comando o acción | Qué observar |
| --- | --- | --- | --- |
| 1 | TimescaleDB | `postgres/examples/01-temporal.sql` | Hypertable; promedios por minuto de CO₂ `802.5` y `812.0`; temperatura media del Aula 204 en las últimas 24 h (siempre devuelve una fila) |
| 2 | PostGIS | `postgres/examples/02-spatial.sql` | `AIR-002` a 0 m y `AMB-001` a ~20 m; a menos de 2 km del Aula 204 hay tres dispositivos y `AMB-005` (a ~10 km) queda afuera |
| 3 | Redis | `sh examples/03-redis.sh` | Clave `iot:last-known:AIR-002` con TTL de hasta 3600 s |
| 4 | SeaweedFS | `run --rm loader` (paso 4) | Bucket y clave del PDF, `PDF=2 páginas`, SHA-256 |
| 5 | bge-m3 | `loader.ingest_vectors` (paso 5) | 4 chunks de 1024 dimensiones |
| 6 | pgvector | `loader.query_vectors` y `postgres/examples/04-vector.sql` | 3 vecinos por similitud; la paráfrasis con `ILIKE` devuelve 0 |
| 7 | RAG | UI o `/api/query` con `"mode": "rag"` | Respuesta con página y sección del manual |
| 8 | Text-to-SQL | UI o `/api/query` con `"mode": "text-to-sql"` | Un único `SELECT` validado sobre `lab_read.measurements` y sus filas |
| 9 | Integrado | UI o `/api/query` con `"mode": "integrated"` | Promedio de telemetría + procedimiento del manual |

Los archivos SQL se ejecutan con el mismo patrón del seed, cambiando el archivo:

```bash
docker compose --env-file .env -f compose.yaml exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' < postgres/examples/01-temporal.sql
```

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

Text-to-SQL corre con un rol de sólo lectura (`ai_readonly`) y un validador: acepta un único `SELECT` sobre las vistas `lab_read.*`, sin `JOIN`, subconsultas ni escrituras. Podés probarlo sin tocar datos preguntando por otra variable (`temperature`, `co2`) u otra ubicación (`LAB-101`).

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
| `APP_PORT`, `POSTGRES_PORT`, `REDIS_PORT`, `SEAWEEDFS_S3_PORT` | `8006`, `5436`, `6379`, `18333` | Puertos publicados en `127.0.0.1` |

`MODELO_EMBEDDING` (`BAAI/bge-m3`) existe, pero no conviene cambiarlo: el esquema `VECTOR(1024)` y el corte coseno están calibrados para ese modelo.

## Experimentar sin perder el punto de partida

- Las consultas de los pasos 1, 2, 6 y de la UI sólo leen: repetilas y cambiá radios, preguntas o `top_k` libremente.
- El loader, `ingest_vectors` y el seed se pueden repetir; no rompen el estado (el seed suma mediciones recientes).
- Si la clave de Redis expiró, volvé a ejecutar `run --rm loader`.
- Para detener conservando datos y caché del modelo: `docker compose --env-file .env -f compose.yaml down`.
- **`down -v` borra todo** (historial, Redis, PDF y el modelo descargado). Usalo sólo si querés empezar de cero; luego repetí el camino rápido.

## Mapa de archivos

| Ruta | Responsabilidad |
| --- | --- |
| [`compose.yaml`](compose.yaml) | Servicios, salud, volúmenes y roles de la demo |
| [`api/`](api/) | FastAPI, UI, cliente OpenRouter y flujos RAG / SQL / integrado |
| [`loader/`](loader/) | PDF inicial, proyección a Redis, indexación vectorial y servicio de carga `uploader` |
| [`shared/`](shared/) | Embeddings, recuperación pgvector y validación SQL |
| [`postgres/init/`](postgres/init/) | Extensiones, tablas, roles y vistas de sólo lectura |
| [`postgres/seed/01-iot.sql`](postgres/seed/01-iot.sql) | Dispositivos, mediciones y registro del manual |
| [`postgres/examples/`](postgres/examples/) | Consultas de TimescaleDB, PostGIS y pgvector |
| [`examples/03-redis.sh`](examples/03-redis.sh) | Lectura de la proyección en Redis |
| [`data/manual-content.json`](data/manual-content.json) | Contenido del manual ENV-X |
| [`tests/`](tests/) | Tests con OpenRouter simulado: `docker compose --env-file .env -f compose.yaml run --rm --entrypoint pytest loader -q` |

## Problemas frecuentes

- **`port is already allocated`:** algún puerto (5436, 6379, 18333, 8006) está ocupado; liberalo o cambialo en `.env`.
- **La primera indexación o carga tarda:** se descarga `BAAI/bge-m3` (~4,3 GB de disco; conviene tener ~10 GB libres). Esperá y repetí el comando si se cortó.
- **`/api/query` dice que falta la clave:** completá `OPENROUTER_API_KEY` en `.env` y recreá `app`. No la imprimas ni la pegues al pedir ayuda.
- **No hay chunks:** ejecutá el loader y luego `loader.ingest_vectors`, en ese orden.
- **Carga con `422`, `413`, `429` o `503`:** PDF inválido, cifrado o sin texto; más de 50 MiB; otra carga en curso; o un servicio caído (`docker compose --env-file .env -f compose.yaml ps`).

## Lista de comprobación

- [ ] Los servicios quedan saludables y `/health` responde `ok`.
- [ ] El seed informa 3 ubicaciones, 4 dispositivos, 1 manual y 104 o más mediciones.
- [ ] TimescaleDB devuelve `802.5` y `812.0` por minuto y el promedio del Aula 204 en 24 h.
- [ ] PostGIS devuelve `AIR-002` y `AMB-001` a 30 m, y excluye `AMB-005` a 2 km.
- [ ] Redis muestra la clave `iot:last-known:AIR-002` con su TTL.
- [ ] El manual queda indexado en 4 chunks de 1024 dimensiones.
- [ ] pgvector devuelve 3 vecinos donde `ILIKE` devuelve 0.
- [ ] RAG cita la sección de recalibración y sin evidencia no llama a OpenRouter.
- [ ] Text-to-SQL muestra un único `SELECT` validado y el modo integrado combina telemetría y manual.
- [ ] Un PDF propio se sube con progreso y un datasheet en inglés responde a una pregunta en español.
