# Presentación: La vida de un dato

Presentación interactiva para la clase de **Arquitectura de Datos**. Recorre
cómo la plataforma aplica series de tiempo, NoSQL, Redis, Row Level Security,
text-to-SQL, RAG, el ciclo de vida de los datos y los backups verificados.

## Abrirla

`index.html` es un único archivo autocontenido: no usa CDN, fuentes web ni
conexiones de red. Se puede copiar a un pendrive y abrir con doble clic en
cualquier navegador moderno (Chrome, Edge o Firefox), sin servidor.

Para preparar la clase, la [guía de estudio](guia-de-estudio.md) explica cada
diapositiva: qué decir, la teoría de fondo, el código y preguntas probables.
También está en [PDF](guia-de-estudio.pdf) para imprimir o leer sin el repositorio.

## Uso

| Tecla | Acción |
| --- | --- |
| `→` `Av Pág` `Espacio` | Siguiente diapositiva |
| `←` `Re Pág` `Mayús`+`Espacio` | Diapositiva anterior |
| `Inicio` / `Fin` | Primera / última |
| `O` | Índice de secciones |
| `B` / `⌫` | Volver a la diapositiva desde la que se saltó (también el botón «↩ Volver» y Atrás del navegador) |
| `T` | Tema claro / oscuro |
| `F` | Pantalla completa |
| `?` | Atajos |
| `Esc` | Cerrar ventanas |

- **Enlaces directos**: `index.html#slide-12` o el nombre de una sección,
  por ejemplo `index.html#seguridad`, `#text-to-sql` o `#backups`.
- **PDF**: imprimir desde el navegador (`Ctrl+P`, "Guardar como PDF"). Sale
  una diapositiva por página, con las decisiones de arquitectura desplegadas.

## Widgets interactivos

Funcionan sin conexión y con datos simulados:

- diagrama de arquitectura (clic en cada servicio);
- recorrido de una lectura paso a paso;
- agregación con `time_bucket` (balde, banda mín–máx, SQL);
- vida de un chunk (compresión y retención);
- Redis caído (degradación a la base);
- simulador de RLS por identidad y la "puerta lateral" de los chunks;
- pipeline de text-to-SQL y la guardia ante SQL malicioso;
- búsqueda por similitud coseno (RAG) y el enrutador del asistente;
- demo de backups verificados.

El guion de la demo en vivo (sección 16) trae los comandos y consultas para
copiar; sus casillas se recuerdan en el navegador.

## Fuentes

El sistema que se presenta es el repositorio [ceiot-app-base](https://github.com/martinlacheski/ceiot-app-base). Los datos
y números salen de su código y de sus documentos
[ciclo de vida de los datos](https://github.com/martinlacheski/ceiot-app-base/blob/main/docs/ciclo-de-vida-datos.md),
[roles de la base](https://github.com/martinlacheski/ceiot-app-base/blob/main/docs/roles-base-de-datos.md),
[backups](https://github.com/martinlacheski/ceiot-app-base/blob/main/docs/backups.md) y
[certificados MQTT](https://github.com/martinlacheski/ceiot-app-base/blob/main/docs/certificados-mqtt.md).
Cada diapositiva cita sus archivos en el pie ("Código: …"), con rutas relativas
a ese repositorio.
