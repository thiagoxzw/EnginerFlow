import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/problem+json" },
  });
}

describe("apiFetch", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("converte erro em ApiError com Problem Details", async () => {
    const problem = {
      type: "about:blank",
      title: "Não autenticado",
      status: 401,
      detail: "Faça login para continuar.",
      instance: "/api/v1/dashboard",
      correlation_id: "abc",
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(401, problem));

    const error = await apiFetch("/api/v1/dashboard").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).problem?.correlation_id).toBe("abc");
    expect((error as ApiError).message).toBe("Faça login para continuar.");
  });

  it("aceita erro sem corpo JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("boom", { status: 502 }));

    const error = await apiFetch("/api/v1/x").catch((e: unknown) => e);

    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).problem).toBeNull();
  });

  it("envia cookies da mesma origem e JSON por padrão", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    await apiFetch("/api/v1/x", { method: "POST", body: "{}" });

    const [, init] = spy.mock.calls[0] as [string, RequestInit];
    expect(init.credentials).toBe("same-origin");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("retorna undefined em 204", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiFetch("/api/v1/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });
});
