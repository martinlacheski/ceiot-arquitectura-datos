# Práctica autónoma de selección y modelado NoSQL

Esta práctica individual presenta un caso IoT **completamente resuelto** desde cuatro representaciones: documental, clave-valor, wide-column y grafo. No es una actividad evaluativa: el laboratorio permite ejecutar los modelos y observar cómo los requerimientos y los patrones de acceso conducen a decisiones distintas sobre los mismos datos.

MongoDB, Redis, Apache Cassandra y Neo4j materializan los cuatro modelos con fines didácticos. Ejecutar los cuatro motores en este laboratorio no constituye una recomendación de arquitectura de producción: la decisión final sigue siendo conservar PostgreSQL cuando sea suficiente y agregar una especialización solo ante una necesidad medible.

## Camino rápido ejecutable

### Herramientas necesarias

| Herramienta | Carácter | Instalación oficial |
| --- | --- | --- |
| Docker Desktop | Recomendado para Windows, macOS y Linux de escritorio. Incluye Docker Engine, Docker CLI y Docker Compose. | [Descargar Docker Desktop](https://docs.docker.com/desktop/) |
| DBeaver Lite | Alternativa gráfica opcional con soporte para Cassandra. Ofrece una prueba gratuita de 14 días sin tarjeta; después requiere una suscripción paga mensual o anual. **DBeaver Community no incluye Cassandra y no sirve para este recorrido.** | [Descargar o probar DBeaver Lite](https://dbeaver.com/dbeaver-lite/#download) · [Suscripción Lite](https://dbeaver.com/products/dbeaver-lite-subscription/) · [Documentación de Cassandra](https://dbeaver.com/docs/dbeaver/Cassandra/) |

No instale MongoDB, Redis, Cassandra, Neo4j, Mongo Express ni RedisInsight por separado: Docker Compose descarga y ejecuta esos componentes. Neo4j Browser viene incorporado en Neo4j y `cqlsh` viene dentro del contenedor de Cassandra, por lo que existe un recorrido completo sin instalar DBeaver.

### Requisitos del entorno

- Una terminal ubicada en `clase-05/practica/`.
- Puertos de host disponibles según las variables `*_HOST_PORT` y enlaces permitidos por las variables `*_BIND_HOST` de `.env`.
- Memoria suficiente para la suma de `MONGO_MEMORY_LIMIT`, `MONGO_EXPRESS_MEMORY_LIMIT`, `REDIS_MEMORY_LIMIT`, `REDISINSIGHT_MEMORY_LIMIT`, `CASSANDRA_MEMORY_LIMIT` y `NEO4J_MEMORY_LIMIT`, más memoria para Docker y el sistema anfitrión. Cassandra también necesita que `CASSANDRA_MAX_HEAP_SIZE` y `CASSANDRA_HEAP_NEWSIZE` sean coherentes con su límite; Neo4j necesita que `NEO4J_HEAP_INITIAL_SIZE`, `NEO4J_HEAP_MAX_SIZE` y `NEO4J_PAGECACHE_SIZE` quepan en el suyo.

El laboratorio requiere más recursos que un único motor. Si Docker no puede sostener simultáneamente los límites configurados, ajuste los valores en `.env` antes de iniciar. Cassandra suele tardar más que los demás servicios en alcanzar el estado saludable; su comprobación contempla un período de arranque prolongado.

### Inicio y comprobación

1. Cree la configuración local a partir de la plantilla. La plantilla contiene valores de desarrollo local; revíselos antes de iniciar y no los reutilice fuera de este laboratorio:

   ```bash
   cp .env.example .env
   ```

2. Inicie los motores y visores persistentes:

   ```bash
   docker compose up -d
   ```

3. Ejecute los cuatro inicializadores, uno por vez y en este orden:

   ```bash
   docker compose run --rm mongo-init
   docker compose run --rm redis-init
   docker compose run --rm cassandra-init
   docker compose run --rm neo4j-init
   ```

   El perfil `init` excluye estas tareas del `up` predeterminado. Al indicar explícitamente un servicio, Compose activa esa tarea aunque pertenezca al perfil; cada dependencia de salud se conserva y el inicializador espera a su motor. El estado de salida de cada comando en la terminal demuestra si terminó correctamente. Con `--rm`, Compose elimina el contenedor al finalizar con éxito, por lo que Docker Desktop conserva solamente los motores y visores persistentes.

4. Compruebe que `mongo`, `redis`, `cassandra` y `neo4j` estén saludables y que no haya contenedores detenidos de inicialización:

   ```bash
   docker compose ps -a
   ```

5. Abra los visores descritos en [Acceso e inspección](#acceso-e-inspección), lea y ejecute los ejemplos nativos `01`, `02` y `03` de cada motor, en ese orden. Después contraste sus salidas con la [comparación final basada en resultados observados](#comparación-final-basada-en-resultados-observados).

6. Al terminar, detenga y retire contenedores y red sin borrar los volúmenes de datos:

   ```bash
   docker compose down
   ```

   Un inicio posterior levanta nuevamente los motores y visores, pero no ejecuta los inicializadores. Repita los cuatro comandos `docker compose run --rm` cuando necesite restaurar o confirmar el estado canónico. Como las semillas son idempotentes, no duplican ese estado. Los volúmenes nombrados permanecen hasta un reinicio destructivo explícito.

> La pregunta no es «¿qué base NoSQL conviene?», sino «¿qué representación responde mejor a este patrón de acceso y qué costo introduce?».

## Configuración del entorno

La configuración variable del laboratorio proviene de `.env`, creado localmente desde `.env.example`:

La mayoría de los repositorios de imágenes usan la etiqueta `latest` directamente en `docker-compose.yml`; no se configuran mediante variables de entorno. MongoDB es la excepción intencional: el motor y su inicializador usan `mongo:7.0.16` porque la verificación de ejecución confirmó que la versión actual de `mongo:latest` rechaza Linux con kernel 6.19 o posterior en el host de prueba. Este resultado es específico de ese host y no implica que la imagen falle en todos los entornos. **Advertencia:** las demás etiquetas `latest` pueden resolver a versiones efectivas diferentes en descargas futuras, lo que reduce la reproducibilidad del laboratorio entre ejecuciones.

| Área | Variables |
| --- | --- |
| Enlaces y puertos de host | `MONGO_BIND_HOST`, `MONGO_HOST_PORT`, `MONGO_EXPRESS_BIND_HOST`, `MONGO_EXPRESS_HOST_PORT`, `REDIS_BIND_HOST`, `REDIS_HOST_PORT`, `REDISINSIGHT_BIND_HOST`, `REDISINSIGHT_HOST_PORT`, `CASSANDRA_BIND_HOST`, `CASSANDRA_HOST_PORT`, `NEO4J_HTTP_BIND_HOST`, `NEO4J_HTTP_HOST_PORT`, `NEO4J_BOLT_BIND_HOST`, `NEO4J_BOLT_HOST_PORT` |
| Credenciales locales | `MONGO_ROOT_USERNAME`, `MONGO_ROOT_PASSWORD`, `MONGO_EXPRESS_USERNAME`, `MONGO_EXPRESS_PASSWORD`, `REDIS_USERNAME`, `REDIS_PASSWORD`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` |
| Nombres lógicos y topología | `MONGO_DATABASE`, `REDIS_DATABASE`, `REDISINSIGHT_ALIAS`, `CASSANDRA_CLUSTER_NAME`, `CASSANDRA_DATACENTER`, `CASSANDRA_RACK`, `CASSANDRA_ENDPOINT_SNITCH`, `CASSANDRA_NUM_TOKENS`, `CASSANDRA_KEYSPACE`, `CASSANDRA_REPLICATION_FACTOR`, `NEO4J_DATABASE` |
| Vigencia | `REDIS_PRESENCE_TTL_SECONDS` |
| Memoria | `MONGO_MEMORY_LIMIT`, `MONGO_EXPRESS_MEMORY_LIMIT`, `REDIS_MEMORY_LIMIT`, `REDISINSIGHT_MEMORY_LIMIT`, `CASSANDRA_MEMORY_LIMIT`, `CASSANDRA_MAX_HEAP_SIZE`, `CASSANDRA_HEAP_NEWSIZE`, `NEO4J_MEMORY_LIMIT`, `NEO4J_HEAP_INITIAL_SIZE`, `NEO4J_HEAP_MAX_SIZE`, `NEO4J_PAGECACHE_SIZE` |

Los puertos internos propios de los productos y los datos canónicos de enseñanza son constantes deliberadas en Compose, scripts y semillas. No deben confundirse con enlaces, puertos, credenciales, nombres lógicos, TTL, topología o memoria configurables desde `.env`.

## Acceso e inspección

Con los valores predeterminados de `.env.example`, los accesos son los siguientes:

| Motor | Herramienta | Acceso predeterminado | Configuración y credenciales |
| --- | --- | --- | --- |
| MongoDB | Mongo Express | [http://localhost:8081](http://localhost:8081) en Chrome, Firefox, Edge u otro navegador externo | El navegador solicitará HTTP Basic Auth: ingrese `MONGO_EXPRESS_USERNAME` y `MONGO_EXPRESS_PASSWORD` definidos en `.env`. La conexión administrativa usa `MONGO_ROOT_USERNAME`, `MONGO_ROOT_PASSWORD` y `MONGO_DATABASE`. |
| Redis | RedisInsight | [http://localhost:5540](http://localhost:5540) | La conexión preparada usa `REDISINSIGHT_ALIAS`, `REDIS_USERNAME`, `REDIS_PASSWORD` y `REDIS_DATABASE` definidos en `.env`. |
| Cassandra | `cqlsh` incluido y recomendado | Ejecute el comando mostrado debajo. Para DBeaver Lite: host `127.0.0.1`, puerto `9042`. | Use el keyspace definido por `CASSANDRA_KEYSPACE`. El laboratorio no configura usuario ni contraseña de Cassandra. |
| Neo4j | Neo4j Browser incorporado | [http://localhost:7474](http://localhost:7474) | Ingrese con `NEO4J_USERNAME`, `NEO4J_PASSWORD` y `NEO4J_DATABASE` definidos en `.env`. La conexión Bolt predeterminada es `bolt://localhost:7687`. |

Estos enlaces corresponden a los puertos publicados en `.env.example` y se enlazan solamente con `127.0.0.1`. Si modifica algún valor `*_BIND_HOST` o `*_HOST_PORT` en `.env`, use la nueva dirección en lugar de la predeterminada. Las credenciales de la plantilla son exclusivamente para desarrollo local.

> **Mongo Express y la pantalla en blanco.** Mongo Express protege su interfaz con HTTP Basic Auth. Algunos navegadores embebidos en editores o IDE —por ejemplo una pestaña llamada *Browser Tab*— no muestran el diálogo de usuario y contraseña: reciben el `401 Unauthorized` esperado y pueden dejar la vista completamente blanca. Abra `http://localhost:8081` en un navegador externo e ingrese `MONGO_EXPRESS_USERNAME` y `MONGO_EXPRESS_PASSWORD` desde `.env`. No coloque usuario ni contraseña dentro de la URL. Si necesita diagnosticarlo, `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8081/` debe devolver `401`; eso confirma que el servicio responde y está esperando autenticación. También puede revisar `docker compose logs mongo-express`.

El camino incluido y sin instalación adicional para Cassandra usa `cqlsh` dentro del servicio:

```bash
docker compose exec cassandra cqlsh localhost 9042
```

## Ejemplos ejecutables en orden

Cada directorio contiene tres pasos: `01` observa el patrón dominante, `02` introduce una variación acotada y `03` recupera el estado canónico. Los montajes de Compose exponen los archivos nativos en `/lab/examples/<motor>/`. **Antes de ejecutar cada paso, abra y lea el archivo:** la consulta o secuencia que se estudia está escrita directamente en el lenguaje del motor.

### MongoDB — P1, agregado documental

```bash
docker compose exec mongo sh -c 'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --file /lab/examples/mongodb/01-p1-read-device.js'
docker compose exec mongo sh -c 'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --file /lab/examples/mongodb/02-p1-safe-variation.js'
docker compose exec mongo sh -c 'mongosh --quiet --username "$MONGO_INITDB_ROOT_USERNAME" --password "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin --file /lab/examples/mongodb/03-p1-recover.js'
```

`01` informa `count=3` y devuelve el único documento de `AIR-002`; el estado canónico contiene **3 documentos**. `02` lleva solo ese documento a `schema_version=3` y agrega `firmware_auto_update`; `03` carga `/lab/database/02-seed.js` y muestra explícitamente `count=3` y `AIR-002` con `schema_version=2`.

### Redis — P2, estado actual por clave

```bash
docker compose exec redis /lab/scripts/run-redis-example.sh /lab/examples/redis/01-p2-read-current.redis
docker compose exec redis /lab/scripts/run-redis-example.sh /lab/examples/redis/02-p2-safe-variation.redis
docker compose exec redis /lab/scripts/run-redis-example.sh /lab/examples/redis/03-p2-recover.redis
```

Inmediatamente después de inicializar hay **12 claves de dispositivo** —cuatro propósitos para cada uno de los tres dispositivos— y un hash de metadatos `lab:schema:device_current`. Las **3 claves `presence`** expiran según `REDIS_PRESENCE_TTL_SECONDS`; por eso, después del TTL quedan nueve claves de dispositivo y el hash. `01` lee el estado, la última medición y la última conexión de `AMB-001`, además del TTL restante. `02` establece para esa presencia una variación de 20 segundos y `03` repone los valores canónicos y el TTL configurado.

Redis no ofrece comentarios ni interpolación de variables de entorno dentro de un flujo nativo de comandos. Por eso, `run-redis-example.sh` es solo un adaptador de transporte acotado: acepta archivos `.redis` del directorio montado, elimina comentarios y líneas vacías, reemplaza únicamente el token fijo del TTL validado y entrega los comandos legibles a `redis-cli`. No evalúa contenido como shell.

### Cassandra — P3, rango temporal particionado

```bash
docker compose exec cassandra sh -c 'cqlsh localhost 9042 --keyspace "$LAB_CASSANDRA_KEYSPACE" --file /lab/examples/cassandra/01-p3-range.cql'
docker compose exec cassandra sh -c 'cqlsh localhost 9042 --keyspace "$LAB_CASSANDRA_KEYSPACE" --file /lab/examples/cassandra/02-p3-safe-variation.cql'
docker compose exec cassandra sh -c 'cqlsh localhost 9042 --keyspace "$LAB_CASSANDRA_KEYSPACE" --file /lab/examples/cassandra/03-p3-recover.cql'
```

La semilla canónica contiene **8 mediciones**. `01` recupera las cinco filas de `AIR-002` para el rango indicado, ordenadas de `10:32:00` a `10:31:00`. `02` escribe dos veces la misma identidad de las `10:30:00` y observa una sola fila, propiedad idempotente de la clave primaria. `03` elimina únicamente esa fila de prueba y ejecuta un `SELECT` explícito que muestra cero filas.

### Neo4j — P4, impacto por relaciones

```bash
docker compose exec neo4j sh -c 'cypher-shell -a bolt://localhost:7687 -u "$LAB_NEO4J_USERNAME" -p "$LAB_NEO4J_PASSWORD" -d "$LAB_NEO4J_DATABASE" -f /lab/examples/neo4j/01-p4-impact.cypher'
docker compose exec neo4j sh -c 'cypher-shell -a bolt://localhost:7687 -u "$LAB_NEO4J_USERNAME" -p "$LAB_NEO4J_PASSWORD" -d "$LAB_NEO4J_DATABASE" -f /lab/examples/neo4j/02-p4-safe-variation.cypher'
docker compose exec neo4j sh -c 'cypher-shell -a bolt://localhost:7687 -u "$LAB_NEO4J_USERNAME" -p "$LAB_NEO4J_PASSWORD" -d "$LAB_NEO4J_DATABASE" -f /lab/examples/neo4j/03-p4-recover.cypher'
```

`01` confirma **8 nodos** —una organización, dos ubicaciones, dos gateways y tres dispositivos— y **8 relaciones**, y encuentra `AIR-002` y `ACT-003` como afectados desde `GW-LAB`. `02` agrega con `MERGE` un enlace de respaldo sin duplicarlo al repetirlo. `03` elimina solo ese enlace y vuelve a 8 nodos y 8 relaciones.

## Inicialización, repetición y recuperación

Los cuatro inicializadores esperan la salud de su motor, aplican primero el esquema y luego la semilla, y terminan. MongoDB usa reemplazos con `upsert` y elimina documentos ajenos al conjunto canónico; Redis sobrescribe sus proyecciones y renueva los TTL; Cassandra repite escrituras con la misma clave primaria; Neo4j usa restricciones y `MERGE`. Por eso pueden repetirse sin acumular copias canónicas.

El perfil `init` mantiene los inicializadores fuera de `docker compose up`: no son procesos permanentes ni dejan contenedores detenidos después de una ejecución correcta. El destino explícito activa cada tarea aunque su perfil no se haya habilitado globalmente. Para inicializar, repetir o recuperar el estado canónico completo, ejecútelos uno por vez y en el mismo orden:

```bash
docker compose run --rm mongo-init
docker compose run --rm redis-init
docker compose run --rm cassandra-init
docker compose run --rm neo4j-init
```

El estado de salida de cada comando en la terminal es la evidencia de éxito; ante un error, la salida permanece disponible en esa misma ejecución. `--rm` elimina el contenedor cuando la tarea termina correctamente. Los archivos nativos `02` y `03` de cada motor son la vía segura para experimentar y recuperar solo el dato modificado. Repetir el inicializador restaura el conjunto canónico completo de ese motor y puede eliminar datos que no pertenezcan a ese conjunto, como ocurre explícitamente en MongoDB.

> **Advertencia — reinicio destructivo total.** El siguiente comando detiene el laboratorio y elimina todos sus volúmenes nombrados, incluidos datos de motores y visores. Úselo solo cuando se desee reconstruir todo desde cero:
>
> ```bash
> docker compose down -v
> ```
>
> Después del borrado, `docker compose up -d` crea volúmenes nuevos para motores y visores. Ejecute luego los cuatro comandos `docker compose run --rm` anteriores para volver a cargar los datos canónicos.

## Caso base: monitoreo ambiental IoT

Una organización opera dispositivos ambientales en dos ubicaciones. Cada dispositivo se conecta mediante un gateway, publica mediciones y mantiene una configuración que depende de su modelo.

### Inventario conocido

| Elemento | Identificador | Datos relevantes |
| --- | --- | --- |
| Organización | `ORG-FIUBA` | Facultad de Ingeniería |
| Ubicación | `AULA-204` | Aula 204 |
| Ubicación | `LAB-101` | Laboratorio 101 |
| Gateway | `GW-AULA` | Conecta los dispositivos del aula |
| Gateway | `GW-LAB` | Conecta los dispositivos del laboratorio |
| Dispositivo | `AMB-001` | Modelo `EnvMonitor-X`; temperatura y humedad |
| Dispositivo | `AIR-002` | Modelo `AirQuality-Pro`; temperatura, humedad y CO₂ |
| Dispositivo | `ACT-003` | Modelo `Ventilation-Actuator`; controla ventilación |

La topología base es la siguiente:

```text
ORG-FIUBA
├── AULA-204
│   └── GW-AULA
│       ├── AMB-001
│       └── ACT-003
└── LAB-101
    └── GW-LAB
        └── AIR-002

ACT-003 depende de las lecturas de AIR-002 para decidir la ventilación.
```

### Requerimientos antes de elegir un modelo

| ID | Necesidad | Garantía o escala relevante |
| --- | --- | --- |
| R1 | Mantener organizaciones, ubicaciones, dispositivos y asignaciones | Integridad referencial y cambios consistentes |
| R2 | Recuperar un dispositivo con su configuración completa | La configuración varía entre modelos y evoluciona por versión |
| R3 | Mostrar el último estado, la última medición y la última conexión | Lectura por identificador, baja latencia y datos reconstruibles |
| R4 | Conservar millones de mediciones por dispositivo | Alta tasa de escritura y crecimiento horizontal solo si el volumen lo exige |
| R5 | Analizar qué componentes se ven afectados por una falla | Recorridos de dependencias de profundidad variable |

### Patrones de acceso dominantes

| ID | Pregunta frecuente | Forma del acceso |
| --- | --- | --- |
| P1 | ¿Cuál es la configuración completa de `AIR-002`? | Lectura de un agregado por `device_id` |
| P2 | ¿Cuál es el último estado conocido de `AMB-001`? | Búsqueda directa por una clave conocida |
| P3 | ¿Qué midió `AIR-002` entre dos instantes, en orden temporal? | Rango por dispositivo y tiempo |
| P4 | Si falla `GW-LAB`, ¿qué dispositivos y dependencias quedan afectados? | Recorrido de relaciones |
| P5 | ¿Qué dispositivos pertenecen a una organización y qué mediciones superan un umbral? | Consulta relacional y agregación flexible |

P1–P4 permiten estudiar modelos especializados. P5 recuerda que el sistema también necesita integridad, transacciones y consultas flexibles: esas necesidades no desaparecen por incorporar NoSQL.

## Criterio común de diseño

Cada propuesta explicita las mismas decisiones:

1. **Necesidad:** problema concreto que se desea resolver.
2. **Patrón de acceso:** consulta que condiciona la estructura.
3. **Identidad:** cómo se encuentra cada dato.
4. **Modelo:** qué se agrupa, ordena, referencia o duplica.
5. **Reglas:** validaciones y sincronización que siguen siendo necesarias.
6. **Límite:** consultas o garantías que el modelo no facilita.

La flexibilidad no elimina el esquema: desplaza parte de sus reglas hacia documentos, claves, particiones, relaciones o código de aplicación.

## Recorrido 1 — Representación documental

### Necesidad y patrón de acceso

**Necesidad:** los modelos de dispositivo tienen configuraciones diferentes y jerárquicas.

**Patrón P1:** obtener un dispositivo junto con toda su configuración a partir de `device_id`.

La unidad natural de lectura es el dispositivo configurado. Por eso se propone una colección conceptual `dispositivos`, con un documento por dispositivo y la configuración embebida.

### Modelo propuesto

```json
{
  "device_id": "AIR-002",
  "schema_version": 2,
  "model": "AirQuality-Pro",
  "location_id": "LAB-101",
  "gateway_id": "GW-LAB",
  "configuration": {
    "sample_interval_seconds": 30,
    "variables": ["temperature", "humidity", "co2"],
    "calibration": {
      "co2_offset_ppm": 12
    },
    "alerts": {
      "co2_max_ppm": 1000
    }
  }
}
```

Para `AMB-001`, el documento puede omitir los campos de CO₂ y usar otra estructura válida:

```json
{
  "device_id": "AMB-001",
  "schema_version": 1,
  "model": "EnvMonitor-X",
  "location_id": "AULA-204",
  "gateway_id": "GW-AULA",
  "configuration": {
    "sample_interval_seconds": 60,
    "variables": ["temperature", "humidity"]
  }
}
```

### Decisiones explícitas

| Decisión | Resolución | Motivo |
| --- | --- | --- |
| Identificador | `device_id` único | P1 comienza por un dispositivo conocido |
| Configuración | Embebida | Se lee y se cambia junto con el dispositivo; no crece sin límite |
| Ubicación y gateway | Referencias por identificador | Tienen vida propia y pueden cambiar independientemente |
| Mediciones | No se embeben | Su crecimiento continuo produciría documentos demasiado grandes |
| Versionado | `schema_version` obligatorio | La aplicación debe interpretar configuraciones antiguas y nuevas |
| Validación | Campos base, tipos y combinaciones por modelo | Flexible no significa aceptar documentos incoherentes |

Una base documental como MongoDB podría materializar esta idea. PostgreSQL con una columna JSONB también podría resolverla si el resto del dominio continúa siendo relacional; almacenar JSON no obliga a adoptar una base documental como modelo principal.

### Observación esperada

P1 se resuelve recuperando una sola unidad que conserva la jerarquía de configuración. `AIR-002` puede incorporar calibración y alertas de CO₂ sin agregar campos vacíos a `AMB-001`.

La ganancia aparece en la correspondencia entre lectura y agregado, no en «guardar cualquier JSON». Todavía deben validarse `device_id`, `schema_version`, intervalos positivos y variables admitidas por cada modelo.

### Variación segura y recuperación

El ejemplo MongoDB `02` cambia `AIR-002` a `schema_version=3` y agrega `"firmware_auto_update": true` dentro de `configuration`. Los otros documentos no cambian, pero una aplicación real debería reconocer la versión 3 y definir el comportamiento de versiones anteriores. El ejemplo `03` reaplica la semilla idempotente y restaura los 3 documentos canónicos.

### Límites y costo aceptado

- Consultar relaciones profundas entre muchos dispositivos sigue siendo incómodo.
- Duplicar nombres de ubicación en cada documento exigiría mantener copias consistentes; por eso solo se conservan referencias.
- Las actualizaciones masivas de una configuración compartida pueden afectar muchos documentos.
- Si la estructura es estable y las consultas combinan entidades, tablas más JSONB pueden resultar suficientes.

## Recorrido 2 — Representación clave-valor

### Necesidad y patrón de acceso

**Necesidad:** responder rápidamente el estado actual de un dispositivo sin recorrer su historial.

**Patrón P2:** se conoce `device_id` y se solicita el último estado, la última medición o la última conexión.

El histórico y el último valor responden preguntas diferentes. La fuente de verdad conserva eventos o mediciones; esta representación mantiene una vista actual reconstruible.

### Modelo propuesto

| Clave | Valor conceptual | Vigencia |
| --- | --- | --- |
| `device:AMB-001:state` | `ONLINE` | Hasta el próximo cambio |
| `device:AMB-001:last_measurement` | `{temperature: 24.6, measured_at: 2025-05-12T10:32:00Z}` | Hasta la próxima medición |
| `device:AMB-001:last_seen` | `2025-05-12T10:32:04Z` | Hasta la próxima conexión |
| `device:AMB-001:presence` | `ONLINE` | Expira según `REDIS_PRESENCE_TTL_SECONDS` |

La convención `device:<device_id>:<purpose>` hace visible la entidad y el propósito. Redis es un ejemplo posible, pero cualquier almacén clave-valor con las garantías requeridas podría implementar el diseño.

### Decisiones explícitas

| Decisión | Resolución | Motivo |
| --- | --- | --- |
| Identidad | Clave compuesta legible | P2 siempre parte de `device_id` y del dato solicitado |
| Granularidad | Una clave por propósito | Cada valor puede actualizarse y expirar de forma independiente |
| Presencia | TTL configurable con `REDIS_PRESENCE_TTL_SECONDS` | La ausencia de señales recientes debe convertirse en `UNKNOWN` |
| Histórico | Permanece fuera | Un único valor no representa una serie temporal |
| Fuente de verdad | Persistencia principal | Los últimos valores pueden reconstruirse desde eventos confirmados |
| Actualización | Escribir después de confirmar la medición | Evita mostrar como durable un dato que aún no fue persistido |

### Observación esperada

Con una clave conocida, la lectura es directa y no necesita filtrar por múltiples atributos. La expiración de `presence` evita conservar indefinidamente un `ONLINE` obsoleto.

Si el almacén temporal pierde su contenido, el sistema puede reconstruir `last_measurement` y `last_seen` desde la persistencia principal. Durante esa reconstrucción puede haber un estado transitorio desactualizado; el producto debe aceptar o señalar esa condición.

### Variación segura y recuperación

El ejemplo Redis `02` reduce a 20 segundos el TTL de `device:AMB-001:presence`. Su resultado permite observar cómo un TTL menor que el intervalo de reporte puede producir falsos estados `UNKNOWN`; el valor operativo se configura con `REDIS_PRESENCE_TTL_SECONDS` y debe contemplar el intervalo esperado y los retrasos de red. El ejemplo `03` reconstruye las vistas canónicas y repone el TTL configurado.

### Límites y costo aceptado

- Buscar «todos los dispositivos con temperatura mayor a 30» no parte de una clave conocida y requiere otro índice o modelo.
- Las relaciones, agregaciones históricas y filtros arbitrarios son poco naturales.
- La duplicación del último valor exige definir orden, reintentos e idempotencia ante eventos demorados.
- Si PostgreSQL satisface la latencia con un índice y una consulta simple, una capa adicional de caché no se justifica.

## Recorrido 3 — Representación wide-column

### Necesidad y patrón de acceso

**Necesidad:** sostener millones de mediciones y una alta tasa de escritura, distribuidas entre nodos si la escala real lo requiere.

**Patrón P3:** obtener las mediciones de un dispositivo durante un período, ordenadas por tiempo.

Aquí «wide-column» significa un modelo distribuido orientado a particiones y familias de columnas, como los que ejemplifican Cassandra o ScyllaDB. No se refiere al almacenamiento columnar analítico.

### Modelo propuesto

```text
measurement_by_device_day

partition_key: (device_id, day)
clustering_order: measured_at DESC, variable ASC
columns: value, unit, quality
```

Filas conceptuales para una partición:

| `device_id` | `day` | `measured_at` | `variable` | `value` | `unit` |
| --- | --- | --- | --- | --- | --- |
| `AIR-002` | `2025-05-12` | `10:32:00Z` | `co2` | `812` | `ppm` |
| `AIR-002` | `2025-05-12` | `10:32:00Z` | `temperature` | `24.6` | `°C` |
| `AIR-002` | `2025-05-12` | `10:31:30Z` | `co2` | `806` | `ppm` |

Para consultar un período de varios días, la aplicación calcula las particiones diarias involucradas, lee cada rango y combina los resultados en orden temporal.

### Decisiones explícitas

| Decisión | Resolución | Motivo |
| --- | --- | --- |
| Clave de partición | `(device_id, day)` | Distribuye dispositivos y acota el crecimiento de cada partición |
| Orden interno | `measured_at DESC` | P3 solicita rangos temporales y suele priorizar lo reciente |
| Variable en el orden | Desempata mediciones simultáneas | Permite varias variables en un mismo instante |
| Metadatos del dispositivo | No se duplican en cada fila | Cambian independientemente y no son necesarios para P3 |
| Consulta por ubicación | Estructura separada solo si es dominante | No se fuerza una consulta ajena a la clave de partición |
| Escritura repetida | Identidad estable por dispositivo, instante y variable | Facilita reintentos sin crear duplicados conceptuales |

### Observación esperada

P3 toca un conjunto predecible de particiones y recupera filas ya ordenadas. El diseño favorece escrituras y rangos conocidos; no intenta ofrecer JOIN ni exploración arbitraria.

Particionar solo por `device_id` concentraría años de datos en una partición creciente. Particionar solo por día reuniría muchos dispositivos y podría crear puntos calientes. La combinación dispositivo-día equilibra acceso y tamaño para este supuesto; los límites reales deben validarse con métricas.

### Variación segura y recuperación

El ejemplo Cassandra `02` reintenta dos veces una escritura con la misma clave primaria y demuestra que conserva una sola fila. El ejemplo `03` elimina únicamente esa fila. Para evaluar otra granularidad de partición —mensual, diaria u horaria— primero deben medirse volumen, tamaño y distribución; esa decisión exige rediseñar el esquema y no forma parte de la variación segura ejecutable.

### Límites y costo aceptado

- Consultas nuevas suelen requerir otra tabla orientada al nuevo acceso y duplicación intencional.
- La aplicación debe mantener consistencia entre representaciones duplicadas.
- Los JOIN tradicionales, recorridos y filtros no previstos no son el objetivo.
- Sin volumen, tasa de escritura o distribución que excedan una solución relacional particionada, este modelo agrega complejidad operativa sin beneficio probado.

## Recorrido 4 — Representación de grafo

### Necesidad y patrón de acceso

**Necesidad:** comprender topología, dependencias y propagación del impacto ante fallas.

**Patrón P4:** partir de un gateway o dispositivo y recorrer relaciones de profundidad variable para encontrar componentes afectados.

### Modelo propuesto

```text
(:Organization {id: "ORG-FIUBA"})
  -[:HAS_LOCATION]-> (:Location {id: "LAB-101"})
  -[:HAS_GATEWAY]->  (:Gateway {id: "GW-LAB"})
  -[:CONNECTS]->      (:Device {id: "AIR-002"})

(:Device {id: "ACT-003"})
  -[:DEPENDS_ON {reason: "ventilation_control"}]->
(:Device {id: "AIR-002"})
```

Los nodos representan entidades con identidad propia. Las relaciones expresan significado y dirección; también pueden tener propiedades. Neo4j es un ejemplo de motor de grafos, no un prerrequisito para razonar sobre esta representación.

### Decisiones explícitas

| Decisión | Resolución | Motivo |
| --- | --- | --- |
| Nodos | Organización, ubicación, gateway y dispositivo | Son entidades identificables y compartidas |
| Relaciones | `HAS_LOCATION`, `HAS_GATEWAY`, `CONNECTS`, `DEPENDS_ON` | Cada conexión expresa una semántica distinta |
| Dirección | Desde contenedor o dependiente hacia su referencia | Hace explícito cómo se recorre cada pregunta |
| Mediciones | Permanecen fuera | El grafo responde topología, no series temporales masivas |
| Identidad | Propiedad `id` única por tipo | Permite vincular el grafo con la fuente principal |
| Sincronización | Cambios de asignación como eventos idempotentes | Evita relaciones duplicadas o topologías antiguas |

### Observación esperada

Si falla `GW-LAB`, un recorrido encuentra `AIR-002`. Al continuar por dependencias, también identifica que `ACT-003` pierde su señal de control aunque se conecte mediante otro gateway.

La ventaja no proviene de tener relaciones —una clave foránea también las representa—, sino de que los caminos variables y el impacto transitivo dominan las consultas.

### Variación segura y recuperación

El ejemplo Neo4j `02` agrega una relación `BACKUP_CONNECTS` desde `GW-AULA` hacia `AIR-002`. La consulta muestra dos gateways para el dispositivo, pero `ACT-003` continúa dependiendo de él. Repetir `MERGE` no duplica el vínculo. El ejemplo `03` elimina solo esa relación y confirma la recuperación de los 8 nodos y 8 relaciones canónicos.

### Límites y costo aceptado

- Relaciones simples 1:N y algunos JOIN conocidos no justifican otro motor.
- Las transacciones del dominio y el histórico de mediciones continúan necesitando una fuente adecuada.
- Mantener una proyección de grafo exige sincronización, monitoreo y recuperación ante eventos perdidos.
- Si P4 es ocasional y la profundidad está acotada, una consulta recursiva en PostgreSQL puede ser suficiente.

## Comparación final basada en resultados observados

Al terminar los cuatro recorridos, comparamos las alternativas utilizando las salidas que produjo el laboratorio. No hay una matriz para completar ni una única tecnología ganadora: la práctica muestra el resultado y explica qué decisión permite justificar.

| Recorrido | Resultado observado | Qué demuestra | Decisión justificada |
| --- | --- | --- | --- |
| MongoDB — documental | `count=3`; `AIR-002` se recuperó como un agregado completo, evolucionó de `schema_version=2` a `3` y volvió a `2` al recuperar. | Un documento conserva estructura jerárquica y permite que una configuración evolucione sin modificar los demás dispositivos, pero todavía necesita validación y versionado. | Resulta razonable para configuraciones variables recuperadas como una unidad. Si el resto del dominio continúa siendo relacional y JSONB resuelve el acceso, PostgreSQL puede seguir siendo suficiente. |
| Redis — clave-valor | Una clave conocida devolvió `ONLINE`, la última medición, la última conexión y un TTL positivo; la variación llevó la presencia a 20 segundos y la recuperación restauró el TTL configurado. | El acceso directo y la expiración representan bien estado actual o presencia. Los valores son una proyección reconstruible, no el histórico ni necesariamente la fuente de verdad. | Resulta útil cuando la baja latencia y la caducidad están justificadas. Si una consulta indexada en PostgreSQL cumple la latencia requerida, agregar Redis puede ser complejidad innecesaria. |
| Cassandra — wide-column | P3 devolvió cinco filas de `AIR-002` ya ordenadas por tiempo; repetir el mismo `INSERT` mantuvo una sola fila y la recuperación mostró cero filas para la variación. | La partición `(device_id, day)` y el orden de clustering responden eficientemente a un rango conocido; una clave primaria completa vuelve idempotente la escritura. | Resulta razonable ante volumen y tasa de escritura que requieran distribución horizontal. Sin evidencia de esa escala, PostgreSQL particionado evita operar otro sistema distribuido. |
| Neo4j — grafo | El grafo canónico mostró 8 nodos y 8 relaciones; desde `GW-LAB` encontró `AIR-002` y el dependiente `ACT-003`; repetir `MERGE` no duplicó la relación de respaldo. | Las relaciones tipadas y los recorridos variables hacen visible el impacto transitivo. La ventaja aparece por la consulta basada en caminos, no por la mera existencia de relaciones. | Resulta útil cuando topología, dependencias y recorridos dominan el producto. Para relaciones 1:N y profundidades acotadas, claves foráneas o consultas recursivas en PostgreSQL pueden alcanzar. |

Esta evidencia permite comparar las alternativas con los mismos criterios arquitectónicos:

| Criterio | Documental | Clave-valor | Wide-column | Grafo |
| --- | --- | --- | --- | --- |
| Problema que resuelve bien | Configuración variable y jerárquica | Último valor por clave conocida | Series masivas por partición y rango | Topología y recorridos de dependencias |
| Identidad principal | `device_id` del documento | Clave `device:<id>:<purpose>` | `(device_id, day)` + tiempo | `id` del nodo y relaciones tipadas |
| Consulta favorecida | Agregado completo | Lectura puntual | Rango temporal previsto | Camino de profundidad variable |
| Duplicación posible | Datos compartidos embebidos | Copia del estado actual | Tablas por patrón de acceso | Proyección de entidades y vínculos |
| Regla crítica | Validar versiones y tipos | TTL, orden e idempotencia | Distribuir particiones y sincronizar copias | Mantener relaciones vigentes |
| Cambio de requerimiento | Puede exigir otro agregado o índice | Puede exigir índices ajenos al modelo | Suele exigir otra tabla | Puede exigir nuevos tipos de relación |
| Límite principal | Cruces y crecimiento del documento | Búsquedas arbitrarias | Consultas no previstas | Datos tabulares o series masivas |

Ninguna columna es ganadora en general. Cada una optimiza una pregunta y acepta costos específicos.

## Decisión de persistencia para el caso

### Cuándo PostgreSQL sigue siendo suficiente

Mantener solo PostgreSQL es la decisión inicial razonable cuando:

- R1 domina y se necesitan integridad, transacciones y consultas flexibles;
- las configuraciones variables caben en JSONB con validaciones claras;
- índices sobre dispositivo y tiempo cumplen P2 y P3 con la latencia requerida;
- el volumen y la tasa de escritura se sostienen con particionado y operación conocida;
- P4 tiene pocos niveles o puede resolverse con JOIN o consultas recursivas;
- no existen métricas que demuestren un cuello de botella.

En ese escenario, una tecnología adicional duplicaría datos y sumaría despliegue, seguridad, monitoreo, respaldo, actualización y conocimiento operativo sin resolver un problema probado.

### Cuándo se justifica agregar otro modelo

Agregar una representación especializada es razonable solo cuando existe un requisito medible que PostgreSQL no satisface de forma aceptable:

| Evidencia observada | Posible complemento | Condición de adopción |
| --- | --- | --- |
| Agregados variables cambian con frecuencia y JSONB complica la mayoría de las lecturas y escrituras | Documental | Definir autoridad, validación, versiones y migración |
| P2 requiere latencia muy baja a gran escala y los valores son reconstruibles | Clave-valor | Aceptar caducidad, fallos de caché y consistencia temporal |
| P3 excede la capacidad operativa medida y requiere escritura distribuida horizontal | Wide-column | Conocer consultas, dimensionar particiones y aceptar duplicación |
| P4 domina el producto y los recorridos variables son costosos o difíciles de mantener | Grafo | Definir sincronización con la fuente de verdad y recuperación |

La evolución puede ser gradual: PostgreSQL como fuente principal y un único complemento para una necesidad concreta. No es necesario incorporar los cuatro modelos ni reemplazar lo que ya funciona.

## Cómo explorar sin perder el punto de partida

- Ejecute primero el paso `01` para reconocer el estado canónico y el patrón P1, P2, P3 o P4 correspondiente.
- Use el paso `02` para cambiar una sola premisa y anticipe qué patrón mejora y cuál empeora.
- Ejecute el paso `03` antes de pasar al motor siguiente; cada recuperación modifica solo la variación documentada.
- Conserve identificadores, unidades, versión y zona horaria al comparar modelos.
- Si una variación obliga a consultar de otra manera, vuelva primero al patrón de acceso y rediseñe desde allí.
- Recurra al inicializador del motor para restaurar todo su conjunto canónico; reserve `docker compose down -v` para un borrado total deliberado.

El objetivo es justificar decisiones mediante una implementación observable, no encontrar una única respuesta correcta ni recomendar cuatro motores para producción.

## Mapa de archivos y recorrido

| Ruta o sección | Responsabilidad |
| --- | --- |
| `.env.example` | Enumera la configuración local que debe copiarse a `.env` y revisarse antes del inicio |
| `docker-compose.yml` | Define motores, visores, salud, dependencias, montajes, puertos y volúmenes |
| `database/` | Contiene esquemas y semillas canónicas para MongoDB, Redis, Cassandra y Neo4j |
| `scripts/` | Contiene los inicializadores idempotentes, su orden esquema-semilla y el adaptador acotado de transporte para Redis |
| `examples/` | Contiene los pasos nativos `01`, `02` y `03`: `.js` para MongoDB, `.redis` para Redis, `.cql` para Cassandra y `.cypher` para Neo4j |
| Caso base | Fija entidades, relaciones y supuestos comunes |
| Requerimientos y patrones | Define el problema antes de la tecnología |
| Recorridos 1–4 | Razona una representación por necesidad dominante y conecta la teoría con el laboratorio |
| Comparación | Hace visibles identificación, consulta, duplicación, reglas y límites |
| Decisión de persistencia | Distingue suficiencia relacional de especialización justificada |

## Lista de comprobación

- [ ] Se creó `.env` desde `.env.example` y se revisó su configuración de desarrollo local.
- [ ] Los cuatro motores alcanzaron el estado saludable, cada inicializador terminó correctamente según el estado de salida de su comando y no quedaron contenedores de inicialización detenidos.
- [ ] Mongo Express, RedisInsight, `cqlsh` y Neo4j Browser permiten inspeccionar los motores correspondientes; DBeaver Lite se utilizó sólo si se optó por su prueba o licencia.
- [ ] MongoDB contiene 3 documentos canónicos y el ejemplo P1 recupera el agregado de `AIR-002`.
- [ ] Redis contiene 12 claves de dispositivo más el hash de metadatos inmediatamente después de inicializar, y se observó la expiración de las 3 claves de presencia según el TTL.
- [ ] Cassandra contiene 8 mediciones canónicas y el ejemplo P3 devuelve el rango ordenado de `AIR-002`.
- [ ] Neo4j contiene 8 nodos y 8 relaciones, y el ejemplo P4 identifica a `AIR-002` y `ACT-003` como afectados.
- [ ] P1–P4 se vincularon respectivamente con agregado documental, lectura por clave, rango particionado y recorrido de relaciones.
- [ ] Cada paso `02` se recuperó con su paso `03` sin borrar los demás datos.
- [ ] Se comprende que `docker compose down` conserva volúmenes y que `docker compose down -v` los elimina de forma destructiva.
- [ ] Cada representación hizo explícitas duplicación, reglas, límites y costos.
- [ ] La decisión final conservó PostgreSQL salvo que una necesidad medible justificara un único modelo complementario.
