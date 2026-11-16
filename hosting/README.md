# AurisCore private engineering hosting

Prepared 2026-11-14. **NOT ONLINE / NOT A CLINICAL MODEL RELEASE.**

Architecture: ESP32 -> existing USB serial bridge on laptop -> outbound WSS ->
hosted gateway -> authenticated HTTPS website / retained CPU Python worker.
The laptop remains necessary for USB acquisition until Wi-Fi firmware is built
and verified. This optional network prototype does not replace the offline-mobile
product requirement. No raw dataset or recorded audio belongs in the deployment.

## What is packaged

- Existing Next standalone application and CPU TensorFlow worker in one container.
- Separate existing gateway container, exact v2 PCM/control contract.
- Caddy HTTPS reverse proxy. Only ports 80/443 are published; gateway and inference
  ports remain internal. The website and ALL inference routes require HTTP Basic
  authentication. WebSocket routes use the pairing protocol and exact origin list.
- Read-only private model mount; startup verifies all three engineering model hash
  inventories. H022 fold1, A005 and L006 fold0 retain their thresholds, source
  normalization, engineering banners and `deployment_eligible=false`.
- No simulator, training service, upload of datasets or automated model promotion.

This is a single-device/team engineering stack. Shared pairing is not a patient
account system. Internet deployment still needs the acceptance checks below.

## Prepare private assets on this laptop

From repository root, with a NEW output directory:

```powershell
AI-Pipeline/.runtime/python/python.exe scripts/prepare_hosting_bundle.py --manifest AI-Pipeline/data/processed/engineering-models/manifest.json --output .runtime/hosting/models-20261114
```

This command has already been run locally. Its `bundle.json` lists nine hashes,
byte counts and source manifest identity. Repeating the command to the same output
is intentionally rejected. Keep that directory private and transfer it separately
to `/opt/auriscore-private/models` on the eventual server. The code image excludes
all model binaries, datasets, local env files and credentials by allowlist.

## Server prerequisites (not provisioned)

An x86-64 Linux VPS with Docker Engine + Compose v2, a domain/subdomain pointing at
its public IP, and inbound TCP 80/443. Exact CPU/RAM sizing requires a real-server
three-model benchmark; the dependency/image memory exceeds the 4.24 MB weights.
Do not purchase a plan based on model file size. No GPU is required by this CPU
inference configuration. Keep SSH administration separate from application ports.

Choose a region near the users and validate WSS stability/RTT there. The current
LAN measurements do not predict internet latency.

## Configure, validate, THEN start (on the Linux server)

1. Transfer reviewed application source, including current uncommitted integration
   changes; cloning current Git HEAD alone omits these changes. Do not copy the
   whole laptop repository (datasets, credentials and research results excluded).
2. Transfer only the private exported model bundle separately. The worker uses UID
   10001: make the mount readable by that UID and inaccessible to unrelated users.
3. Copy `hosting/hosting.env.example` to ignored `hosting/hosting.env`. Replace ALL
   placeholders. Set a NEW randomly generated pairing token (at least 32 random
   bytes), not the token shared during LAN testing. Generate it on the server and
   privately save it; never put credentials in Git, URLs, build args or chat.
4. Generate a password hash interactively: `docker run --rm -it caddy:2 caddy hash-password`.
   Store the bcrypt hash single-quoted in `AURISCORE_WEB_PASSWORD_HASH` so dollar
   signs remain literal. Use a separate strong password for website login.
5. From repository root:

```sh
docker compose --env-file hosting/hosting.env -f hosting/compose.yaml config --quiet
docker compose --env-file hosting/hosting.env -f hosting/compose.yaml build
docker compose --env-file hosting/hosting.env -f hosting/compose.yaml run --rm --no-deps proxy caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file hosting/hosting.env -f hosting/compose.yaml up -d
docker compose --env-file hosting/hosting.env -f hosting/compose.yaml ps
```

Avoid `compose config` without `--quiet`: it prints resolved secrets. DNS and valid
TLS must work before transferring any real body audio. Never disable certificate
validation. On Linux, record `docker image inspect` IDs and `pip freeze` in private
acceptance evidence: base image tags and transitive Python dependencies are not yet
fully digest-locked. No exact Linux/Windows inference parity is claimed.

## Laptop-to-server USB bridge

First stop the LOCAL serial bridge to release COM3; do not run two serial readers.
Keep the local services as a fallback. Save the NEW server token in a local private
file, separate from `.runtime/hardware/pairing-token.txt`, then run:

```powershell
AI-Pipeline/.runtime/python/python.exe -u scripts/serial_to_gateway.py --port COM3 --gateway wss://YOUR_DOMAIN/device --token-file C:/PRIVATE/server-pairing-token.txt
```

`YOUR_DOMAIN` and the private file path are placeholders. Do not run this command
until a real server has passed acceptance. HTTPS website gateway defaults to
`wss://YOUR_DOMAIN/browser` on port 443; the LAN HTTP default remains port 8082.
The site first asks for its website login, then the device pairing code. Only one
browser controls the device. Physical audio is sent off the laptop only when this
remote bridge is deliberately selected; none has been uploaded during preparation.

## Mandatory server acceptance before use

- Container build/typecheck and valid TLS; no plain-HTTP audio fallback.
- Anonymous UI and `/api/analysis*` requests return 401; authenticated ones work.
- Wrong pairing/origin rejected; one controller enforced; controller handoff and
  USB/Wi-Fi loss stop recording without fabricated samples.
- Private mount hashes pass; all three models load and return finite results on
  generated synthetic inputs, with engineering-only labels. Save Linux versions,
  image IDs, peak RAM and inference durations; compare against the same saved
  synthetic inputs on the laptop before claiming runtime portability.
- iPhone Safari listening/recording, real bridge source continuity, five-minute
  WSS transport, reconnect and latest-window backpressure pass.
- No audio or token in logs, no datasets in image; only Caddy ports published.

Stop/rollback on the server with `docker compose --env-file hosting/hosting.env -f
hosting/compose.yaml down` (do not add `-v`). Return the bridge to the original local
gateway and original local token file. No research checkpoint or model is overwritten.
