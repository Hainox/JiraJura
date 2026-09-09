# ODH API Proxy Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the GitHub Pages ODH map API route across JiraJura deployments without coupling either application's database or lifecycle.

**Architecture:** JiraJura's nginx proxy owns a small, versioned `/odh-api/` reverse-proxy snippet. Both TLS and bootstrap server configurations include that snippet; Docker renders it as a separate nginx config file. The independently deployed ODH API joins JiraJura's existing Docker network under the fixed alias `odh-sao-api` and is never built or controlled by JiraJura.

**Tech Stack:** Docker Compose v2, nginx 1.30 Alpine templates, Bash, GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-09-09-odh-api-proxy-design.md`

## Global Constraints

- Preserve the public API base URL `https://obhod-sao.ru/odh-api/`.
- Do not publish ODH port `8787` on the host.
- Do not add ODH code, credentials, database access, or lifecycle management to JiraJura.
- Keep tracked files clean on the server so `deploy-watcher.sh` can run.
- Verify the proxy configuration before any production restart.

---

### Task 1: Version the ODH route and mount it into nginx

**Files:**
- Create: `deploy/nginx/odh-api.conf.template`
- Modify: `deploy/nginx/proxy.conf.template`
- Modify: `deploy/nginx/http-only.conf.template`
- Modify: `docker-compose.prod.yml`
- Test: `deploy/tests/test_odh_proxy_config.sh`

**Interfaces:**
- Consumes: Docker DNS alias `odh-sao-api` on the Compose network `jirajura_default`.
- Produces: nginx location `/odh-api/` forwarding stripped-path requests to `http://odh-sao-api:8787`.

- [ ] **Step 1: Write the failing static configuration test**

```bash
#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
snippet="$root/deploy/nginx/odh-api.conf.template"
grep -Fq 'location /odh-api/' "$snippet"
grep -Fq 'set $odh_api_upstream odh-sao-api:8787;' "$snippet"
grep -Fq 'proxy_pass http://$odh_api_upstream$uri$is_args$args;' "$snippet"
grep -Fq 'include /etc/nginx/conf.d/odh-api.conf;' "$root/deploy/nginx/proxy.conf.template"
grep -Fq 'include /etc/nginx/conf.d/odh-api.conf;' "$root/deploy/nginx/http-only.conf.template"
grep -Fq './deploy/nginx/odh-api.conf.template:/etc/nginx/templates/odh-api.conf.template:ro' "$root/docker-compose.prod.yml"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash deploy/tests/test_odh_proxy_config.sh`

Expected: FAIL because the snippet and mounts do not exist.

- [ ] **Step 3: Implement the isolated route**

Create this nginx snippet:

```nginx
location /odh-api/ {
    set $odh_api_upstream odh-sao-api:8787;
    rewrite ^/odh-api/(.*)$ /$1 break;
    proxy_pass http://$odh_api_upstream$uri$is_args$args;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Insert `include /etc/nginx/conf.d/odh-api.conf;` after the Docker resolver in
both server configurations. Mount the template in the `proxy` service so the
standard nginx entrypoint renders it at container startup.

- [ ] **Step 4: Run static and Compose validation**

Run:

```bash
bash deploy/tests/test_odh_proxy_config.sh
docker compose -f docker-compose.prod.yml config >/dev/null
```

Expected: both commands exit `0`.

- [ ] **Step 5: Commit the feature**

```bash
git add deploy/nginx/odh-api.conf.template deploy/nginx/proxy.conf.template \
  deploy/nginx/http-only.conf.template docker-compose.prod.yml \
  deploy/tests/test_odh_proxy_config.sh
git commit -m "feat(deploy): isolate ODH API proxy route"
```

### Task 2: Document network attachment and production verification

**Files:**
- Modify: `deploy/README.md`
- Modify: `deploy/scripts/deploy-watcher.sh`
- Test: `deploy/tests/test_odh_proxy_config.sh`

**Interfaces:**
- Consumes: route emitted by Task 1 and an ODH API health path supplied by the ODH service owner.
- Produces: repeatable server instructions that keep the ODH route alive and verify it without exposing port `8787`.

- [ ] **Step 1: Extend the failing static test for watcher verification**

Add assertions that the watcher invokes `deploy/scripts/verify-odh-proxy.sh`
after proxy restart and records its output in the deploy log.

- [ ] **Step 2: Run the test to verify it fails**

Run: `bash deploy/tests/test_odh_proxy_config.sh`

Expected: FAIL because no ODH proxy verifier is invoked.

- [ ] **Step 3: Add a bounded verifier and deployment documentation**

Create `deploy/scripts/verify-odh-proxy.sh`. It must read `DOMAIN` and the
optional `ODH_HEALTH_PATH` from `.env`. When the variable is empty, print that
ODH verification is skipped and exit `0`; when it is non-empty but does not
start with `/`, exit nonzero. For a valid non-empty path, issue:

```bash
curl --fail --silent --show-error \
  "https://${DOMAIN}/odh-api${ODH_HEALTH_PATH}"
```

Invoke it after `$COMPOSE restart proxy` in `deploy-watcher.sh`. Document the
external network attachment for the ODH compose project:

```yaml
services:
  api:
    networks:
      jirajura_proxy:
        aliases: [odh-sao-api]
networks:
  jirajura_proxy:
    external: true
    name: jirajura_default
```

Document server checks: `docker network inspect jirajura_default`, the HTTPS
health request, and `git status --short` before a deploy.

- [ ] **Step 4: Run all checks**

Run:

```bash
bash deploy/tests/test_odh_proxy_config.sh
docker compose -f docker-compose.prod.yml config >/dev/null
bash -n deploy/scripts/deploy-watcher.sh deploy/scripts/verify-odh-proxy.sh
git diff --check
```

Expected: every command exits `0`.

- [ ] **Step 5: Commit the operations documentation and verifier**

```bash
git add deploy/README.md deploy/scripts/deploy-watcher.sh \
  deploy/scripts/verify-odh-proxy.sh deploy/tests/test_odh_proxy_config.sh
git commit -m "docs(deploy): verify ODH API proxy health"
```

### Task 3: Full regression, PR, and controlled rollout

**Files:**
- Modify: none

**Interfaces:**
- Consumes: commits from Tasks 1–2.
- Produces: a CI-verified PR and exact production rollout sequence.

- [ ] **Step 1: Run repository checks**

Run:

```bash
docker compose -f docker-compose.prod.yml config >/dev/null
bash deploy/tests/test_odh_proxy_config.sh
git diff --check
```

Expected: every command exits `0`.

- [ ] **Step 2: Create PR and wait for CI**

Create a PR from `agent/odh-api-proxy-integration` into `main`. Confirm CI
passes before merge.

- [ ] **Step 3: Deploy only after merge**

On the server:

```bash
cd /opt/jirajura
git pull --ff-only origin main
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml restart proxy
curl --fail --silent --show-error "https://obhod-sao.ru/odh-api${ODH_HEALTH_PATH:-/health}"
docker compose -f docker-compose.prod.yml ps
```

Expected: the ODH request succeeds and all JiraJura containers are running.
