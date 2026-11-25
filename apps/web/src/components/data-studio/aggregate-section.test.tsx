import { describe, expect, it } from "vitest";

import {
  aggregateReady,
  buildAggregateBody,
  type Measure,
} from "@/components/data-studio/aggregate-section";

describe("buildAggregateBody", () => {
  it("envia colunas de agrupamento e medidas na ordem escolhida", () => {
    const measures: Measure[] = [
      { column: "SYN-Valor", op: "sum" },
      { column: "SYN-Código", op: "count_distinct" },
    ];
    expect(
      buildAggregateBody({ datasetId: "ds-1", groupBy: ["SYN-Grupo"], measures }),
    ).toEqual({
      dataset_id: "ds-1",
      group_by: ["SYN-Grupo"],
      measures: [
        { column: "SYN-Valor", op: "sum" },
        { column: "SYN-Código", op: "count_distinct" },
      ],
    });
  });

  it("aceita agrupamento vazio (total geral)", () => {
    expect(
      buildAggregateBody({
        datasetId: "ds-1",
        groupBy: [],
        measures: [{ column: "SYN-Valor", op: "count" }],
      }).group_by,
    ).toEqual([]);
  });
});

describe("aggregateReady", () => {
  it("exige pelo menos uma medida com coluna escolhida", () => {
    expect(aggregateReady([])).toBe(false);
    expect(aggregateReady([{ column: "", op: "count" }])).toBe(false);
    expect(aggregateReady([{ column: "SYN-Valor", op: "sum" }])).toBe(true);
  });
});
