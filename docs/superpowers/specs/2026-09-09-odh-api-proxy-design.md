# ODH API proxy isolation design

## Goal

Keep the public ODH map on GitHub Pages able to send district corrections through
`https://obhod-sao.ru/odh-api/`, while allowing JiraJura to deploy from `main`
without a server-only modification blocking the deployment watcher or being
overwritten.

## Context

JiraJura owns the public reverse proxy on `obhod-sao.ru`.  The ODH map is a
separate application; its API container is named `odh-sao-api` and listens on
port `8787`.  It is not part of the JiraJura database or compose stack.

The production proxy currently has an uncommitted `location /odh-api/` block.
The deploy watcher intentionally refuses to run when a tracked file is dirty,
and also synchronizes the active proxy configuration from the repository.

## Chosen architecture

1. JiraJura version-controls only the reverse-proxy boundary:
   `deploy/nginx/odh-api.conf` contains the ODH `location` block.
2. `proxy.conf.template` and `http-only.conf.template` both include that
   generated snippet inside their `server` blocks, so TLS and first-install
   configurations expose the same route.
3. The `proxy` service mounts the snippet read-only at
   `/etc/nginx/odh-api.conf`. It is outside nginx's automatically included
   `conf.d` directory and is included only from the intended `server` blocks.
4. The ODH API must join the external Docker network named `jirajura_default`
   with the alias `odh-sao-api`.  JiraJura does not start, stop, or rebuild the
   ODH service.
5. The deploy watcher continues to build/restart JiraJura and proxy.  Its
   normal configuration sync now preserves the ODH route because the route is
   part of `main`.

## Request flow

```text
GitHub Pages map -> https://obhod-sao.ru/odh-api/* -> JiraJura proxy -> odh-sao-api:8787
JiraJura UI      -> https://obhod-sao.ru/api/v1/*  -> JiraJura api:8000
```

The proxy strips the `/odh-api/` prefix before forwarding.  It sends standard
forwarded headers but does not expose the ODH container port to the Internet.

## Failure behavior

- A request to JiraJura remains independent from ODH availability.
- An unavailable ODH container causes only `/odh-api/*` to return `502`; no
  JiraJura API or database request is routed to ODH.
- Nginx resolves `odh-sao-api` through Docker DNS every ten seconds, allowing
  an ODH container restart without restarting JiraJura proxy.
- A deploy verification checks JiraJura root, its API, and—when explicitly
  configured—an ODH endpoint. The ODH health path is never guessed: an empty
  `ODH_HEALTH_PATH` logs that ODH verification was skipped without failing a
  JiraJura release; a non-empty value must start with `/` and is verified via
  the public proxy.

## Acceptance criteria

- `git status --short` remains clean after a normal JiraJura deployment.
- `/api/v1/*` still reaches JiraJura API and `/odh-api/*` reaches only ODH.
- The ODH port `8787` is not published externally.
- The server can restart `proxy` and continue serving the map route.
- CI validates nginx configuration structure and the deployment instructions.

## Out of scope

- Moving the GitHub Pages map into JiraJura.
- Sharing JiraJura's PostgreSQL credentials or schema with ODH.
- Changes to ODH application code, its database, or map UI.
