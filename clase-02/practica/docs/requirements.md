# Requerimientos del caso IoT

Una organización administra dispositivos instalados en ubicaciones. Cada dispositivo registra mediciones ambientales a lo largo del tiempo. Las personas pueden pertenecer a varias organizaciones con un rol de negocio. El sistema debe conservar cambios de estado y de ubicación para reconstruir el pasado.

## Reglas que se modelan

| Regla | Decisión física |
| --- | --- |
| Una organización tiene nombre estable | `organizations.name` es único |
| Un usuario puede pertenecer a varias organizaciones | `organization_users` resuelve la relación N:M |
| Un dispositivo pertenece a una organización | FK obligatoria `devices.organization_id` |
| Un número de serie no se repite | `devices.serial_number` es único |
| Un dispositivo puede cambiar de ubicación | `device_location_history` conserva intervalos `[started_at, ended_at)` |
| Una medición pertenece directamente a un dispositivo | FK obligatoria `measurements.device_id`; no existe entidad `Sensor` |
| El pasado importa | las tablas de historial son append-oriented y no sobrescriben eventos |

## Alcance deliberado

`organization_id` expresa propiedad y permite filtrar ejemplos y consultas. **No es una frontera de seguridad en esta práctica.** No hay login, autorización, permisos, `TenantContext` ni RLS: esos mecanismos pertenecen a la clase de seguridad y escalabilidad.

## Evolución posterior, no implementada

- **PostGIS:** reemplazar `latitude`/`longitude` por geometrías y consultas espaciales cuando el caso las requiera.
- **TimescaleDB:** evaluar hypertables, retención y agregados cuando el volumen temporal lo justifique.
- **pgVector:** evaluar embeddings sólo si aparece una necesidad de búsqueda semántica.
