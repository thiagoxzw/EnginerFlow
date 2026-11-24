"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError, login } from "@/lib/api";

const schema = z.object({
  email: z.email({ message: "Informe um e-mail válido." }),
  password: z.string().min(1, { message: "Informe a senha." }),
});

type LoginValues = z.infer<typeof schema>;

export interface LoginFormProps {
  onSuccess?: () => void;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  const onSubmit = async (values: LoginValues) => {
    setServerError(null);
    try {
      await login(values.email, values.password);
      if (onSuccess) {
        onSuccess();
      } else {
        router.replace("/");
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setServerError("E-mail ou senha inválidos.");
      } else {
        setServerError("Não foi possível entrar. Verifique se a API está em execução.");
      }
    }
  };

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      noValidate
      className="w-full max-w-sm space-y-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-6"
      aria-describedby={serverError ? "login-error" : undefined}
    >
      <h1 className="text-xl font-semibold">Entrar no EngiFlow</h1>

      <div className="space-y-1">
        <label htmlFor="email" className="block text-sm font-medium">
          E-mail
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          aria-invalid={errors.email ? "true" : "false"}
          aria-describedby={errors.email ? "email-error" : undefined}
          className="w-full rounded-md border border-[var(--color-border)] bg-transparent px-3 py-2"
          {...register("email")}
        />
        {errors.email ? (
          <p id="email-error" className="text-sm text-[var(--color-danger)]">
            {errors.email.message}
          </p>
        ) : null}
      </div>

      <div className="space-y-1">
        <label htmlFor="password" className="block text-sm font-medium">
          Senha
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={errors.password ? "true" : "false"}
          aria-describedby={errors.password ? "password-error" : undefined}
          className="w-full rounded-md border border-[var(--color-border)] bg-transparent px-3 py-2"
          {...register("password")}
        />
        {errors.password ? (
          <p id="password-error" className="text-sm text-[var(--color-danger)]">
            {errors.password.message}
          </p>
        ) : null}
      </div>

      {serverError ? (
        <p id="login-error" role="alert" className="text-sm text-[var(--color-danger)]">
          {serverError}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-md bg-[var(--color-accent)] px-4 py-2 font-medium text-white disabled:opacity-60"
      >
        {isSubmitting ? "Entrando…" : "Entrar"}
      </button>
    </form>
  );
}
