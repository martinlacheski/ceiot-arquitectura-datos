# SearchableSelect

Select controlado, filtrable y de selección única con valores por defecto en español. Copie el directorio completo en un proyecto React de cliente.

## Ruta rápida

1. Instale dependencias.
2. Conserve el árbol de directorios.
3. Controle `value` y actualícelo desde `onChange`.

## Dependencias

```bash
npm install @radix-ui/react-dialog @radix-ui/react-popover @radix-ui/react-slot class-variance-authority clsx cmdk lucide-react tailwind-merge
```

React y React DOM son peer requirements.

## Uso

```tsx
import { useState } from "react";
import { SearchableSelect } from "./components/searchable-select/SearchableSelect";

const [city, setCity] = useState<string>();

<SearchableSelect
  options={[{ value: "montevideo", label: "Montevideo" }]}
  value={city}
  onChange={setCity}
  placeholder="Seleccionar ciudad..."
/>;
```

No requiere provider ni store global. Debe renderizarse en un árbol React con capacidad de cliente porque usa estado y overlays del navegador.

## Tailwind, accesibilidad e i18n

Los primitives locales usan tokens semánticos y utilidades de animación de estilo shadcn. Configure el escaneo de Tailwind para este directorio; los portales de Radix se montan en `document.body`. El trigger expone estado de combobox y Command permite filtrar y navegar con teclado. La acción de limpiar conserva un `role="button"` anidado en el trigger; revíselo frente a la política de accesibilidad del destino. Localice juntos placeholder, búsqueda y estado vacío.

## Checklist de adaptación

- [ ] Copié el árbol completo, incluidas ambas rutas locales de `cn`.
- [ ] Instalé dependencias y configuré tokens y escaneo Tailwind.
- [ ] Rendericé desde un componente de cliente y controlo `value`/`onChange`.
- [ ] Verifiqué el apilamiento de portales sin agregar niveles `z-index` manuales.
- [ ] Proveí textos localizados.
