# Duka Manager — web frontend (Next.js)

The owner dashboard and a web POS for the FastAPI backend in `../backend`. One app, role-aware:
owners see everything; cashiers see Sell (POS), Sales, Products and Customers.

## Run it

Start the backend first (from `../backend`: `uv run uvicorn app.main:app --reload`), then:

```sh
npm install
npm run dev          # http://localhost:3000
```

The browser only talks to this app: `/api/*` is proxied to the backend (`BACKEND_URL`, default
`http://localhost:8000`), so the backend needs no CORS setup.

The system serves one shop. The first visit sets the shop up (shop name and owner); after that,
sign-in is "who is working?". This is a dev stub standing in for owner OTP and cashier PIN login.
The owner adds cashiers under Settings → Users.

## API types

`src/lib/api-schema.d.ts` is generated from the backend's OpenAPI schema. After any backend API
change:

```sh
npm run gen:api      # needs uv; writes openapi/openapi.json and the types
```

Then `npm run typecheck` shows every page that needs updating.

## Checks

```sh
npm run typecheck
npm run lint
npm run build
```
