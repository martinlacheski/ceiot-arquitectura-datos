export type ConfirmCallback = () => void | Promise<void>;

type ConfirmState = {
  isOpen: boolean;
  message: string;
  onConfirm: ConfirmCallback;
};

let state: ConfirmState = {
  isOpen: false,
  message: "",
  onConfirm: () => undefined,
};

const listeners = new Set<() => void>();

function update(next: Partial<ConfirmState>) {
  state = { ...state, ...next };
  listeners.forEach((listener) => listener());
}

export const confirmStore = {
  getState: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  openConfirm(message: string, onConfirm: ConfirmCallback) {
    update({ isOpen: true, message, onConfirm });
  },
  closeConfirm() {
    update({ isOpen: false });
  },
};

export function showConfirmDialog(message: string, onConfirm: ConfirmCallback) {
  confirmStore.openConfirm(message, onConfirm);
}
