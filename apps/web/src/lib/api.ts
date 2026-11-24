/** Cliente HTTP da API local. Erros chegam como Problem Details (RFC 9457). */

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string;
  correlation_id?: string | null;
  errors?: { loc: string[]; msg: string; type: string }[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem | null;

  constructor(status: number, problem: Problem | null) {
    super(problem?.detail ?? `Falha na requisição (HTTP ${status})`);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }
}

export interface UserOut {
  email: string;
  display_name: string;
}

export interface AuditEntryOut {
  occurred_at: string;
  action: string;
  resource: string;
  result: string;
}

export interface DashboardOut {
  user: UserOut;
  system: { version: string; database: string };
  activity_last_7_days: number;
  recent_activity: AuditEntryOut[];
  note: string;
}

async function parseProblem(response: Response): Promise<Problem | null> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "title" in body) {
      return body as Problem;
    }
  } catch {
    // corpo que não é JSON: segue sem detalhes
  }
  return null;
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  if (!response.ok) {
    throw new ApiError(response.status, await parseProblem(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function login(email: string, password: string): Promise<UserOut> {
  return apiFetch<UserOut>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
}

export function getDashboard(): Promise<DashboardOut> {
  return apiFetch<DashboardOut>("/api/v1/dashboard");
}
