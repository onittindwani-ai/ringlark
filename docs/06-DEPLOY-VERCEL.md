# Deploy the web app on Vercel

Vercel hosts only the **web** part. The API and worker need a server that stays on (Railway or Hetzner, or any host that runs Docker). **Not tested by me: I did not deploy to Vercel.** The steps come from Vercel's docs (see `facts/hosting.md`).

1. Put the API online first (`07` or `08`) and note its address, such as `https://api.yourdomain.com`.
2. In Vercel, import your Git repository.
3. Set **Root Directory** to `apps/web`.
4. Turn on **Include source files outside of the Root Directory in the Build Step**. The web app uses the shared `packages/ui-kit`, which sits outside `apps/web`.
5. Framework preset: Next.js. Install command: `pnpm install`. Build command: `pnpm build` (Vercel runs it inside `apps/web`).
6. Set environment variable `API_BASE_URL` to your API address (no trailing slash).
7. Do **not** set `INSECURE_COOKIES` or `NEXT_PUBLIC_DEMO_HINT`.
8. Deploy. Open the address, sign in.
9. On the API server, make sure uvicorn runs with `--proxy-headers` and the environment variable `FORWARDED_ALLOW_IPS` set to your proxy's address (the Docker image reads it; never `*`), so rate limits see the real visitor and not Vercel.

## Webhooks

Telnyx and Ultravox must call the **API** directly (`https://api.yourdomain.com/api/webhooks/...`), and Ultravox reaches the agent tool endpoints at `https://api.yourdomain.com/api/tools/...`. Not the Vercel address. The web app deliberately forwards only the API paths its pages use, so `webhooks`, `tools` and `auth/login` are refused there.

## If the build fails

Most common: the ui-kit folder was not included (step 4), or `pnpm-workspace.yaml` does not list `packages/*`. See `15`.
