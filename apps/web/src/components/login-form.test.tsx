import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const loginMock = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, login: (...args: unknown[]) => loginMock(...args) };
});

describe("LoginForm", () => {
  afterEach(() => {
    loginMock.mockReset();
  });

  it("mostra erros de validação sem chamar a API", async () => {
    render(<LoginForm onSuccess={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByText("Informe um e-mail válido.")).toBeInTheDocument();
    expect(screen.getByText("Informe a senha.")).toBeInTheDocument();
    expect(loginMock).not.toHaveBeenCalled();
  });

  it("envia credenciais válidas e chama onSuccess", async () => {
    loginMock.mockResolvedValue({ email: "a@example.com", display_name: "A" });
    const onSuccess = vi.fn();
    render(<LoginForm onSuccess={onSuccess} />);

    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "segredo-123" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1));
    expect(loginMock).toHaveBeenCalledWith("a@example.com", "segredo-123");
  });

  it("exibe mensagem genérica quando a API recusa o login", async () => {
    const { ApiError } = await import("@/lib/api");
    loginMock.mockRejectedValue(new ApiError(401, null));
    render(<LoginForm onSuccess={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("E-mail"), { target: { value: "a@example.com" } });
    fireEvent.change(screen.getByLabelText("Senha"), { target: { value: "errada" } });
    fireEvent.click(screen.getByRole("button", { name: "Entrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha inválidos.");
  });
});
