import { fileURLToPath } from "node:url";
import type { NextConfig } from "next";

// Content security policy. Next.js pages carry inline scripts and styles, so those two stay allowed ('unsafe-inline'); everything else is limited to this
// site: no scripts, styles, images, fonts or connections from other sites, no plugins, no framing, no change of the base address, forms post only here.
// `next dev` also needs eval for hot reload, so it is added outside production builds only.
const DEV = process.env.NODE_ENV !== "production";
const CSP = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${DEV ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "media-src 'self' blob:",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const config: NextConfig = {
  transpilePackages: ["@sendora/ui-kit"],
  reactStrictMode: true,
  poweredByHeader: false,
  // Only Docker builds ask for the standalone folder (NEXT_STANDALONE=1); a normal build works with `next start`.
  output: process.env.NEXT_STANDALONE === "1" ? "standalone" : undefined,
  async headers() {
    // Defence in depth for the browser. The session cookie is already httpOnly and sameSite=lax.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: CSP },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
  outputFileTracingRoot: fileURLToPath(new URL("../../", import.meta.url)),
};

export default config;
