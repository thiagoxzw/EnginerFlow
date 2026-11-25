"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { CompareTab, CrossSection, ExplodeTab, HistoryTab, KitsTab, ValidateTab } from "@/components/bom/bom-analysis";
import { ImportAssistant } from "@/components/bom/bom-import";
import { TreeView } from "@/components/bom/bom-tree-view";
import { getBomLines, listBomStructures, setBomCurrent, type BomStructure } from "@/lib/bom";
import { topLines } from "@/lib/bom-tree";
import { usePersistedString } from "@/lib/persist";
import { errorText } from "@/components/data-studio/templates-section";

const TABS = [
  { id: "visao", label: "Visão geral" },
  { id: "estrutura", label: "Estrutura" },
  { id: "explosao", label: "Explosão de materiais" },
  { id: "comparacao", label: "Comparação" },
  { id: "validacao", label: "Validação" },
  { id: "kits", label: "Kits" },
  { id: "historico", label: "Histórico" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export const BOM_STRUCTURE_KEY = "engiflow:bom-estrutura";

export function BomView() {
  const queryClient = useQueryClient();
  const structures = useQuery({ queryKey: ["bom-structures"], queryFn: listBomStructures });
  const [storedId, setStoredId] = usePersistedString(BOM_STRUCTURE_KEY);
  const [workingRevision, setWorkingRevision] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("visao");
  const [focusLine, setFocusLine] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const structure: BomStructure | undefined = structures.data?.find((s) => s.id === storedId) ?? structures.data?.[0];
  const revisionId = workingRevision ?? structure?.current_revision_id ?? null;
  const lines = useQuery({
    queryKey: ["bom-lines", revisionId],
    queryFn: () => getBomLines(revisionId as string),
    enabled: Boolean(revisionId),
  });
  const data = lines.data?.lines ?? [];
  const current = structure?.revisions.find((r) => r.id === revisionId);
  const parent = structure?.revisions.find((r) => r.id === current?.parent_revision_id);
  const next = structure?.revisions.find((r) => r.number === (current?.number ?? 0) + 1);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ["bom-structures"] });
  }

  function open(s: BomStructure) {
    setStoredId(s.id);
    setWorkingRevision(null);
    setMessage(null);
  }

  function adopt(s: BomStructure) {
    setStoredId(s.id);
    setWorkingRevision(s.current_revision_id);
    void refresh();
  }

  async function move(target: { id: string } | undefined) {
    if (!structure || !target) return;
    setMessage(null);
    try {
      const updated = await setBomCurrent(structure.id, target.id);
      setWorkingRevision(updated.current_revision_id);
      await refresh();
    } catch (error) {
      setMessage(errorText(error));
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="space-y-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-y-auto">
        <section aria-labelledby="bom-lista" className="space-y-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <h2 id="bom-lista" className="font-medium">Estruturas</h2>
          {structures.isPending ? <p className="text-sm text-[var(--color-muted)]">Carregando…</p> : null}
          {structures.data && structures.data.length === 0 ? (
            <p className="text-sm text-[var(--color-muted)]">Nenhuma estrutura ainda. Importe uma abaixo.</p>
          ) : null}
          <ul className="divide-y divide-[var(--color-border)]">
            {(structures.data ?? []).map((s) => (
              <li key={s.id} className="py-2">
                <button
                  type="button"
                  onClick={() => open(s)}
                  aria-pressed={s.id === structure?.id}
                  className="w-full text-left text-sm"
                >
                  <strong className="block truncate">{s.name}</strong>
                  <span className="text-xs text-[var(--color-muted)]">{s.revisions.length} revisão(ões)</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <ImportAssistant onCreated={(id) => { setStoredId(id); setWorkingRevision(null); void refresh(); }} />
      </aside>

      <main className="min-w-0 space-y-4">
        <header className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-xl font-semibold">BOM Manager</h1>
          <p className="text-xs text-[var(--color-muted)]">Nada é alterado automaticamente: cada edição cria uma nova revisão.</p>
        </header>

        {!structure ? (
          <p className="text-sm text-[var(--color-muted)]">Importe uma estrutura para começar. A prévia aparece antes de qualquer gravação.</p>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <strong>{structure.name}</strong>
              <span className="text-[var(--color-muted)]">
                · revisão de trabalho: r{current?.number ?? "—"}{current?.id === structure.current_revision_id ? " (atual)" : ""}
              </span>
              <button type="button" className="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs disabled:opacity-50" disabled={!parent} onClick={() => void move(parent)}>
                Desfazer (revisão anterior)
              </button>
              <button type="button" className="rounded-md border border-[var(--color-border)] px-2 py-1 text-xs disabled:opacity-50" disabled={!next} onClick={() => void move(next)}>
                Refazer (revisão seguinte)
              </button>
            </div>
            {message ? <p role="alert" className="text-sm text-[var(--color-danger)]">{message}</p> : null}

            <div role="tablist" aria-label="Seções do BOM Manager" className="flex flex-wrap gap-1 border-b border-[var(--color-border)]">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={`px-3 py-2 text-sm ${tab === t.id ? "border-b-2 border-[var(--color-accent)] font-medium" : "text-[var(--color-muted)]"}`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {!revisionId || lines.isPending ? (
              <p className="text-sm text-[var(--color-muted)]">Carregando estrutura…</p>
            ) : lines.isError ? (
              <p role="alert" className="text-sm text-[var(--color-danger)]">{errorText(lines.error)}</p>
            ) : (
              <div role="tabpanel" aria-label={TABS.find((t) => t.id === tab)?.label}>
                {tab === "visao" ? (
                  <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-4">
                    <dt className="text-[var(--color-muted)]">Linhas</dt>
                    <dd className="font-mono">{data.length}</dd>
                    <dt className="text-[var(--color-muted)]">Topos</dt>
                    <dd className="font-mono">{topLines(data).length}</dd>
                    <dt className="text-[var(--color-muted)]">Revisões</dt>
                    <dd className="font-mono">{structure.revisions.length}</dd>
                    <dt className="text-[var(--color-muted)]">Origem</dt>
                    <dd>{current?.source_dataset_id ? "tabela do Data Studio" : "—"}</dd>
                  </dl>
                ) : null}
                {tab === "estrutura" ? (
                  <TreeView
                    key={`focus-${focusLine ?? "none"}`}
                    revisionId={revisionId}
                    lines={data}
                    focusLine={focusLine}
                    onNewRevision={(id) => { setWorkingRevision(id); void refresh(); }}
                  />
                ) : null}
                {tab === "explosao" ? <ExplodeTab revisionId={revisionId} lines={data} /> : null}
                {tab === "comparacao" ? <CompareTab structure={structure} /> : null}
                {tab === "validacao" ? (
                  <div className="space-y-6">
                    <ValidateTab
                      revisionId={revisionId}
                      mode={current?.mode ?? "explicit"}
                      onGoto={(line) => {
                        setFocusLine(line);
                        setTab("estrutura");
                      }}
                    />
                    <CrossSection revisionId={revisionId} />
                  </div>
                ) : null}
                {tab === "kits" ? <KitsTab structure={structure} revisionId={revisionId} /> : null}
                {tab === "historico" ? (
                  <HistoryTab structure={structure} onUse={adopt} onOpen={(id) => { setWorkingRevision(id); setTab("estrutura"); }} />
                ) : null}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
