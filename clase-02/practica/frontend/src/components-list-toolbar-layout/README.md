# ListToolbarLayout

Cápsula React para alinear búsqueda y acciones de una lista sin acoplarla a tabla, router o store.

## Instalación

```bash
npm install react
npm install -D tailwindcss
```

El destino debe procesar las clases Tailwind v4 o equivalentes. Copie ambos archivos y conserve su relación local.

## Importación y uso

```tsx
import { ListToolbarLayout } from "./ListToolbarLayout";

<ListToolbarLayout
  search={<input aria-label="Buscar elementos" data-list-toolbar-search-control />}
  primaryActions={<button type="button">Crear elemento</button>}
  secondaryActions={<button type="button">Limpiar filtros</button>}
/>;
```

## Accesibilidad y responsive

- En móvil apila búsqueda y acciones; desde `md` las alinea en fila.
- `flex-wrap` evita desbordes con etiquetas largas.
- Los botones descendientes reciben altura mínima de 44 px (`min-h-11`).
- Marque el control real de búsqueda con `data-list-toolbar-search-control`.
- Cada slot debe proporcionar nombre accesible, foco y semántica correcta.

## Checklist de adaptación

- [ ] El input tiene label visible o `aria-label`.
- [ ] Las acciones usan `<button>` o primitives accesibles.
- [ ] Los tokens y clases Tailwind existen en el destino.
- [ ] Se probaron etiquetas largas y viewport móvil.
- [ ] `data-testid` se conserva cuando la estrategia de pruebas lo requiere.
