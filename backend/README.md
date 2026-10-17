# Product backend

Shared product services: accounts, authorization, devices, connector credentials, imports/sync, Kit registration and application settings. [channels](channels/README.md) contains server-side channel adapters.

Start with modules in one backend. Split deployment units when operational requirements justify it; module names are not a promise of separate microservices.

The backend maps product identity to Oath's `user_id`, exposes a safe client integration path and brokers authorized access to Nostalgia and Kits. Oath owns execution state; Nostalgia owns Context storage and retrieval. The backend must not replace either core.

Framework, database and authentication provider remain undecided. No API server or login flow is implemented yet.
