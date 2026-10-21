# Hymio operator console

This is a standalone React/Vite application for operators. It is served at `/admin/` by the
cloud Web image and uses `/auth/*` plus `/admin/api/*` on the same origin. It does not share
navigation, state or visual components with the user Web application.

The current module manages cloud-resource entitlements, capacity and lifecycle. Future
operations modules can be added without changing the product clients.

## Development

Run Backend on `127.0.0.1:8080`, then:

```sh
pnpm --filter @hymio/admin dev
```

Open `http://127.0.0.1:1421/admin/`. The Vite proxy forwards `/auth` and `/admin/api` to Backend.
Sign in with a product account whose ID is listed in `admin_user_ids`.

Every operation is checked server-side. This application never reads provider credentials or
the database directly.
