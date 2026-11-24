import type { NextConfig } from "next";

const apiUrl = process.env.ENGIFLOW_API_URL ?? "http://127.0.0.1:8000";

// Mesma origem para o navegador: /api/v1/* é encaminhado para a API local.
// Assim o cookie de sessão (HttpOnly, SameSite=Lax) funciona sem CORS no fluxo normal.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${apiUrl}/api/v1/:path*` }];
  },
};

export default nextConfig;
