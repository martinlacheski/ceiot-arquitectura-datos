# Arquitectura de Datos

Repositorio académico con materiales disponibles de las clases 1 a 6 para recorrer el ciclo de vida del dato: desde su generación e ingreso hasta su persistencia, consulta, especialización e integración segura con IA.

## Organización de la materia

| Clase | Eje conceptual | Material |
| --- | --- | --- |
| 1 | Del dato a la persistencia y recuperación | [Clase 1](clase-01/README.md) · [Práctica](clase-01/practica/README.md) |
| 2 | Modelado y consultas sobre datos persistidos | [Clase 2](clase-02/README.md) · [Práctica](clase-02/practica/README.md) |
| 3 | SQL aplicado sobre datos IoT persistidos | [Presentación](clase-03/Clase%203%20Presentacion.pdf) · [Práctica](clase-03/practica/README.md) |
| 4 | Modelado, índices y evolución de esquema | [Práctica](clase-04/practica/README.md) |
| 5 | Selección y modelado NoSQL | [Práctica](clase-05/practica/README.md) |
| 6 | Datos especializados e IA: series temporales, geoespacial, caché, objetos, carga e inspección de PDF, vectores, RAG y Text-to-SQL | [Práctica](clase-06/practica/README.md) |
| 7–8 | Continuación de la arquitectura de datos | Próximamente |

## Documentos del repositorio

- [`CONTRIBUTING.md`](CONTRIBUTING.md): convenciones para crear y mantener la documentación, incluido el uso de diagramas Mermaid.
- `programa-materia/`: fuente versionada del programa, alcance y objetivos académicos de la materia.
- `clase-XX/README.md`: presentación y acceso al material de cada clase implementada.
- `clase-XX/practica/README.md`: guía pública y autocontenida de la práctica.
- `clase-03/practica/sql/`: recorrido progresivo de ejemplos SQL resueltos sobre el modelo IoT.
- `clase-06/practica/api/`: backend FastAPI, proxy de carga, catálogo y UI para inspeccionar PDF, respuestas, SQL, fuentes y trazas.
- `clase-06/practica/loader/`: ingestión reproducible del PDF inicial, servicio interno para cargas, proyección Redis e indexación vectorial.
- `clase-06/practica/shared/`: catálogo de documentos, E5 local, recuperación pgvector y frontera segura de Text-to-SQL compartida.

El recorrido recomendado comienza con la [práctica de Clase 1](clase-01/practica/README.md) para seguir un dato desde su ingreso hasta su recuperación. Continúa con la [práctica de Clase 2](clase-02/practica/README.md) para modelado, la [práctica de Clase 3](clase-03/practica/README.md) para SQL, la [práctica de Clase 4](clase-04/practica/README.md) para índices y evolución, y la [práctica de Clase 5](clase-05/practica/README.md) para seleccionar modelos NoSQL desde patrones de acceso. La [práctica de Clase 6](clase-06/practica/README.md) agrega especializaciones temporales, espaciales, clave-valor, objetos y vectores; permite cargar e inspeccionar PDF con proveniencia y límites observables, y recién entonces integra RAG y Text-to-SQL.
