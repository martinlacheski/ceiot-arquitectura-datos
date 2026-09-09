# Práctica autónoma de SQL con datos IoT

Esta práctica individual ofrece ejemplos SQL **completamente resueltos** para ejecutar, observar y modificar libremente. No son ejercicios evaluativos ni se entrega una solución: cada consulta canónica ya es runnable. El entorno es independiente de Clase 2, reutiliza su modelo relacional y su seed determinista de 72 mediciones, y se concentra en PostgreSQL, pgAdmin y un cliente Python mínimo.

## Camino rápido con pgAdmin

1. Desde `clase-03/practica`, copie la configuración de ejemplo: `cp .env.example .env`.
2. Inicie PostgreSQL y pgAdmin: `docker compose up -d`.
3. Abra [http://localhost:5051](http://localhost:5051).
4. Inicie sesión con `student@example.edu` / `class3-local` (o sus valores de `.env`).
5. Registre el servidor descrito abajo y abra **Tools → Query Tool**.
6. Ejecute los archivos de [`sql/`](sql/) en orden. Puede seleccionar una sentencia o ejecutar el archivo completo.

> La interfaz principal es pgAdmin. La terminal solo se usa para iniciar servicios y, al final, demostrar parámetros del driver Python.

## Conectar pgAdmin a PostgreSQL

En pgAdmin, haga clic derecho en **Servers → Register → Server...**:

| Pestaña/campo | Valor predeterminado |
| --- | --- |
| General → Name | `ceiot-clase-03` |
| Connection → Host name/address | `postgres` |
| Connection → Port | `5432` |
| Connection → Maintenance database | `ceiot_class3` |
| Connection → Username | `ceiot` |
| Connection → Password | `ceiot` |

`postgres` es el nombre interno del servicio Compose; dentro de pgAdmin no use `localhost`. Después, abra **Databases → ceiot_class3 → Schemas → public → Tables** para reconocer el esquema. La inicialización crea dos organizaciones, cinco ubicaciones, seis dispositivos, siete filas de historial de estado (seis actuales) y exactamente **72 mediciones canónicas**. `Future Station C` queda intencionalmente sin asignación actual para hacer observable un join externo; el estado cerrado de mantenimiento de `CEIOT-A-01` precede, sin solaparse, a su estado activo actual.

Comprobación rápida en Query Tool:

```sql
SELECT COUNT(*) AS canonical_measurement_count
FROM measurements;
```

El resultado esperado es `72`.

## Recorrido progresivo

Cada archivo sigue el mismo ritmo: **contexto → ejemplo ejecutable → observación esperada → variaciones seguras → recuperación**. Las variaciones son invitaciones para jugar; no hay consignas pendientes, espacios en blanco, TODO ni soluciones ocultas.

| Orden | Archivo | Qué observar |
| --- | --- | --- |
| 1 | [`01-inspeccion-y-restricciones.sql`](sql/01-inspeccion-y-restricciones.sql) | Tablas, atributos, vocabulario relacional, PK, FK, UNIQUE y CHECK |
| 2 | [`02-select-y-filtros.sql`](sql/02-select-y-filtros.sql) | SELECT, IN, BETWEEN, AND/OR, NULL, rangos temporales y orden estable |
| 3 | [`03-agregaciones.sql`](sql/03-agregaciones.sql) | COUNT, MIN, MAX, AVG, GROUP BY, WHERE y HAVING |
| 4 | [`04-joins-subconsulta-cte.sql`](sql/04-joins-subconsulta-cte.sql) | INNER, LEFT, RIGHT y FULL OUTER JOIN, agregación, subconsulta y CTE |
| 5 | [`05-ventanas-lag.sql`](sql/05-ventanas-lag.sql) | `LAG` particionado por dispositivo y variable |
| 6 | [`06-ddl-dml-seguro.sql`](sql/06-ddl-dml-seguro.sql) | INSERT simple/múltiple, UPDATE, DELETE, restricciones, CASCADE y RESTRICT |
| 7 | [`07-transacciones.sql`](sql/07-transacciones.sql) | BEGIN, COMMIT, ROLLBACK y verificación posterior |
| 8 | [`08-errores-y-buenas-practicas.sql`](sql/08-errores-y-buenas-practicas.sql) | Errores frecuentes capturados y sus alternativas seguras |

Los primeros cinco archivos son de solo lectura. Los archivos 6 a 8 contienen cambios controlados en la tabla auxiliar `measurement_annotations`; cuando el ejemplo necesita una fila descartable de `measurements`, la crea y elimina dentro de una transacción que termina en `ROLLBACK`. Los ejemplos de `UPDATE` y `DELETE` hacen visible su alcance y restauran o eliminan sus cambios temporales. Ningún ejemplo altera las **72 mediciones canónicas**.

## Cómo experimentar sin perder el punto de partida

- Ejecute primero la consulta canónica y compare con **OBSERVACIÓN ESPERADA**.
- Cambie un filtro, alias, fecha u orden usando las **VARIACIONES SEGURAS**.
- En DML, conserve el `WHERE id = ...` y ejecute también la sección de recuperación.
- Antes y después de una mutación, confirme `SELECT COUNT(*) FROM measurements;`: debe seguir en `72`.
- Si interrumpe el archivo de transacciones antes de finalizar, ejecute `ROLLBACK;` en la misma pestaña de Query Tool.
- Para restaurar la nota auxiliar canónica, vuelva a ejecutar `06-ddl-dml-seguro.sql`; es repetible.

El objetivo es explorar el efecto de cambios pequeños y leer los resultados, no resolver desafíos ni entregar respuestas.

## Consulta parametrizada desde Python

[`client/query.py`](client/query.py) pasa un literal SQL estático con marcadores `%s` directamente a `cursor.execute(..., parameters)` y entrega los valores por separado. No concatena entradas dentro del SQL. Esto es parametrización del driver, distinta de interpolar strings.

Con PostgreSQL ya iniciado, ejecute el servicio de perfil:

```bash
docker compose --profile client run --build --rm query-client
```

Con los parámetros predeterminados se listan cuatro temperaturas de `CEIOT-A-01`, ordenadas por fecha, y al final aparece `rows=4`. Para probar otros valores sin editar código:

```bash
DEVICE_SERIAL=CEIOT-B-01 VARIABLE=co2 \
  docker compose --profile client run --build --rm query-client
```

Las fechas usan un rango semiabierto: `START_AT` está incluido y `END_AT` excluido. Los valores predeterminados están documentados en `.env.example`.

## Mapa del entorno

| Ruta | Responsabilidad |
| --- | --- |
| [`docker-compose.yml`](docker-compose.yml) | PostgreSQL, pgAdmin y cliente Python opcional |
| [`database/01-schema.sql`](database/01-schema.sql) | Esquema relacional IoT adaptado de Clase 2 |
| [`database/02-seed.sql`](database/02-seed.sql) | Seed determinista e idempotente, incluidas 72 mediciones |
| [`sql/`](sql/) | Ejemplos SQL progresivos y resueltos |
| [`client/query.py`](client/query.py) | Consulta parametrizada mínima con psycopg |

Los volúmenes `postgres_data` y `pgadmin_data` conservan base y configuración entre reinicios. Los scripts de inicialización se ejecutan al crear por primera vez el volumen de PostgreSQL. Esta clase no cubre optimización profunda, migraciones ni evolución de esquema.

## Lista de comprobación

- [ ] pgAdmin conecta con el host `postgres`.
- [ ] `SELECT COUNT(*) FROM measurements;` devuelve `72`.
- [ ] Los ocho scripts SQL se ejecutan en orden sin completar código faltante.
- [ ] Después de `08-errores-y-buenas-practicas.sql`, la nota canónica conserva su texto original.
- [ ] El cliente Python muestra `rows=4` con los parámetros predeterminados.
