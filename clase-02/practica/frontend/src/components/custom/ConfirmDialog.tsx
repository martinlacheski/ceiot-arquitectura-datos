import { useState, useSyncExternalStore } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../ui/alert-dialog";
import { Spinner } from "../ui/spinner";
import { confirmStore } from "../../store/confirm.store";

export function ConfirmDialog() {
  const confirmation = useSyncExternalStore(
    confirmStore.subscribe,
    confirmStore.getState,
  );
  const [isPending, setIsPending] = useState(false);

  async function handleConfirm() {
    const currentCallback = confirmation.onConfirm;
    setIsPending(true);
    try {
      await currentCallback();
      if (confirmStore.getState().onConfirm === currentCallback) {
        confirmStore.closeConfirm();
      }
    } catch {
      // The mutation flow keeps its existing error feedback and remains open.
    } finally {
      setIsPending(false);
    }
  }

  return (
    <AlertDialog
      open={confirmation.isOpen}
      onOpenChange={(open) => {
        if (!open && !isPending) confirmStore.closeConfirm();
      }}
    >
      <AlertDialogContent aria-busy={isPending}>
        <AlertDialogHeader>
          <AlertDialogTitle>Confirmación</AlertDialogTitle>
          <AlertDialogDescription>
            {confirmation.message}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            disabled={isPending}
            onClick={confirmStore.closeConfirm}
          >
            No
          </AlertDialogCancel>
          <AlertDialogAction
            disabled={isPending}
            onClick={() => void handleConfirm()}
          >
            {isPending ? <Spinner data-icon="inline-start" /> : null}
            {isPending ? "Procesando…" : "Sí"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
