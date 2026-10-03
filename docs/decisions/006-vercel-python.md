# Vercel without leaving Python

## Decision

Sawt on Vercel stays in Python. There is no Next.js app. The page is static HTML. Each `/api/*` route is a short Python function. Words live in Supabase Postgres, scoped by a Clerk `user_id`.

## Why

The old process was a long-running `ThreadingHTTPServer` and a local SQLite file. Vercel does not keep a process up, and serverless disk is not durable. The language was never the problem.

I write Python, so the move is handlers + a database, not a rewrite in another stack. Supabase is the free Postgres host: same `DATABASE_URL`, no extra client SDK.

## How

1. `api/*.py` handlers call the same `lexicon/` code as local serve.
2. `DATABASE_URL` opens Supabase Postgres (`lexicon/db.py`). On Vercel, use the Transaction pooler URI (port 6543); prepared statements are off for that pooler. Without `DATABASE_URL`, local serve still uses SQLite with a `user_id` column (`local` on this machine).
3. Clerk signs the browser in. The page sends `Authorization: Bearer …`. Python checks the JWT against `CLERK_JWKS_URL` and uses `sub` as `user_id`.
4. OpenRouter models and the voice loop are unchanged; only the host of the HTTP calls moves.
