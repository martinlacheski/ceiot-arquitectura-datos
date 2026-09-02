import { CircleAlertIcon, CircleCheckIcon } from "lucide-react";

import {
  Alert,
  AlertAction,
  AlertDescription,
  AlertTitle,
} from "../../components/ui/alert";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

export function ResourceFeedback({
  error,
  success,
  onRetry,
}: {
  error: string;
  success: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      {error ? (
        <Alert variant="destructive">
          <CircleAlertIcon />
          <AlertTitle>No se pudieron mostrar los datos.</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <AlertAction>
            <Button
              id="retry-resource"
              type="button"
              variant="outline"
              size="sm"
              onClick={onRetry}
            >
              Reintentar
            </Button>
          </AlertAction>
        </Alert>
      ) : null}
      {success ? (
        <Alert role="status">
          <CircleCheckIcon />
          <AlertTitle>Registro creado</AlertTitle>
          <AlertDescription>
            <Badge variant="secondary">{success}</Badge>
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}
