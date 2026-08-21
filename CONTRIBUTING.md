# Convenciones de documentación

Estas pautas mantienen los archivos Markdown claros, consistentes y adecuados para estudiantes.

## Diagramas

Usar Mermaid como opción predeterminada frente a diagramas ASCII complejos cuando una representación visual mejore la comprensión de una arquitectura, un flujo, una secuencia, una relación o un proceso. Cuando la compatibilidad entre visores sea importante, guardar la fuente editable en un archivo `.mmd`, generar un SVG y referenciarlo desde Markdown.

Antes de agregar un diagrama, comprobar que:

- aporta más claridad que una frase, una lista o una tabla y no cumple una función meramente decorativa;
- es pequeño y legible, mantiene una dirección de flujo coherente y usa etiquetas explícitas en las conexiones;
- emplea nombres comprensibles para estudiantes y solamente tecnologías ya introducidas;
- diferencia protocolos y responsabilidades, por ejemplo HTTP/JSON entre clientes y API, y SQL entre backend y base de datos;
- no sugiere que una base de datos expone endpoints de API;
- usa sintaxis Mermaid ampliamente compatible, sin estilos ni extensiones especiales innecesarios;
- está acompañado por texto que explique las responsabilidades representadas y la conclusión principal.

El ASCII simple sigue siendo aceptable para estructuras triviales o en entornos donde Mermaid no renderiza.

## Regeneración

Ejecutar desde la raíz del repositorio, reemplazando las rutas por las del diagrama correspondiente:

```bash
npx -y @mermaid-js/mermaid-cli \
  -i clase-01/practica/docs/diagrams/arquitectura.mmd \
  -o clase-01/practica/docs/diagrams/arquitectura.svg
```

Editar siempre el archivo `.mmd` y volver a generar el SVG; no editar el SVG manualmente. Versionar ambos archivos y mantener en Markdown una referencia relativa al SVG junto con un enlace breve a la fuente.

Al modificar documentación, revisar que los enlaces relativos funcionen y que cada bloque de código tenga su cierre correspondiente.
