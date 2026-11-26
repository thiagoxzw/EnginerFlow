import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-[var(--color-bg)] p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-[var(--color-accent)] text-lg font-bold text-white" aria-hidden="true">
            E
          </span>
          <div>
            <p className="font-semibold tracking-tight">EngiFlow</p>
            <p className="text-sm text-[var(--color-muted)]">Automação de engenharia · uso individual</p>
          </div>
        </div>
        <LoginForm />
      </div>
    </main>
  );
}
