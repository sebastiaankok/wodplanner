# Client-side sessions via signed cookie

User sessions are stored entirely client-side as a signed, serialised cookie (`itsdangerous URLSafeTimedSerializer`). There is no sessions table in the database.

This was chosen for simplicity: no session store to maintain, no cleanup job, horizontally stateless. The trade-off is that sessions cannot be revoked server-side — a stolen or leaked cookie is valid until it expires naturally. For a personal household tool this is an acceptable risk; a multi-tenant product would need server-side session records.

**Consequence:** Changing `SECRET_KEY` invalidates all active sessions immediately (every user is logged out). In production, `SECRET_KEY` must be set explicitly and treated as stable.
