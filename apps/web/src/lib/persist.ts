"use client";

import { useCallback, useSyncExternalStore } from "react";

const CHANGE_EVENT = "engiflow:persist";

/** Chave da tabela aberta no Data Studio: sobrevive a atualizar a página, neste navegador. */
export const SELECTED_TABLE_KEY = "engiflow:tabela-selecionada";

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // armazenamento indisponível: a seleção vale só até atualizar
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // sem armazenamento a seleção não persiste, mas a tela continua funcionando
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: key }));
}

/**
 * Valor persistido por chave, lido de forma compatível com a renderização no servidor
 * (no servidor retorna null; a leitura real acontece no navegador, sem divergência de hidratação).
 */
export function usePersistedString(key: string): [string | null, (value: string | null) => void] {
  const subscribe = useCallback(
    (notify: () => void) => {
      const onChange = (event: Event) => {
        if (event instanceof CustomEvent && event.detail !== key) return;
        notify();
      };
      window.addEventListener(CHANGE_EVENT, onChange);
      window.addEventListener("storage", onChange);
      return () => {
        window.removeEventListener(CHANGE_EVENT, onChange);
        window.removeEventListener("storage", onChange);
      };
    },
    [key],
  );
  const value = useSyncExternalStore(
    subscribe,
    () => read(key),
    () => null,
  );
  const setValue = useCallback((next: string | null) => write(key, next), [key]);
  return [value, setValue];
}
