import { ResourcePanel } from "../modules/resources/ResourcePanel";
import { resources } from "../modules/resources/catalog";

export function App() {
  return (
    <main className="page-shell">
      <header className="page-header">
        <p className="eyebrow">Clase 2 · Arquitectura de datos</p>
        <h1>Modelo de datos IoT</h1>
        <p>
          Explore flujos de listado y alta. Los IDs expresan propiedad del caso,
          no autenticación ni autorización.
        </p>
      </header>
      <section className="resource-grid" aria-label="Recursos del modelo IoT">
        {resources.map((resource) => (
          <ResourcePanel key={resource.endpoint} resource={resource} />
        ))}
      </section>
    </main>
  );
}
