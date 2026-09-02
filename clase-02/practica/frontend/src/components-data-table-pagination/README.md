# DataTablePagination

Controles de paginación reutilizables para una instancia de TanStack Table. Copie el directorio completo en un proyecto React de cliente.

## Ruta rápida

1. Instale las dependencias.
2. Mantenga `ui/` y `lib/` junto a `DataTablePagination.tsx`.
3. Pase una instancia `table` configurada.

## Árbol

```text
DataTablePagination.tsx
lib/utils.ts
ui/button.tsx
ui/button-variants.ts
ui/select.tsx
README.md
```

## Dependencias

```bash
npm install @tanstack/react-table @radix-ui/react-select @radix-ui/react-slot class-variance-authority clsx lucide-react tailwind-merge
```

React y React DOM son peer requirements.

## Uso

```tsx
import { getCoreRowModel, getPaginationRowModel, useReactTable } from "@tanstack/react-table";
import { DataTablePagination } from "./components/data-table-pagination/DataTablePagination";

const table = useReactTable({
  data,
  columns,
  getCoreRowModel: getCoreRowModel(),
  getPaginationRowModel: getPaginationRowModel(),
});

<DataTablePagination table={table} totalItems={total} entityName="elementos" />;
```

La tabla debe habilitar paginación mediante `getPaginationRowModel`. Para paginación de servidor, provea `totalItems`.

## Tailwind, accesibilidad e i18n

Los primitives usan tokens semánticos estilo shadcn, como `bg-background`, `text-muted-foreground` y `border-input`. Configure el escaneo de Tailwind para este directorio. Los controles incluyen etiquetas de lector de pantalla con `sr-only`; conserve esa utilidad. Los textos visibles están en español: reemplácelos de forma consistente para otro idioma.

## Checklist de adaptación

- [ ] Copié todo el árbol sin cambiar rutas relativas.
- [ ] Instalé dependencias y configuré tokens semánticos.
- [ ] La tabla tiene modelo de paginación.
- [ ] Verifiqué objetivos táctiles y textos localizados.
