# AurisCore Vercel engineering deployment

The WebApp also uses Supabase Auth, Postgres and private WAV Storage for
optional cross-phone accounts and session history.
See [accounts and history](../../WebApp/docs/accounts-and-history.md) for
configuration and ownership rules. Account data does not go to the inference
deployment.

The ESP32 opens a TLS WebSocket to the WebApp. The browser pairs over a second
WebSocket. The gateway relays unmodified v2 PCM16 frames and capture controls
through Redis Pub/Sub. The browser sends live PCM windows or recorded WAV to
the same-origin analysis API, which forwards them to a dedicated Vercel Python
Function. Guest history stays in the browser; signed-in sessions synchronize
results and private WAVs to Supabase. Redis stores only short-lived
connection leases. Audio is published without replay or server-side recording.

Use synthetic audio for this engineering deployment. Public-cloud handling of
patient recordings requires a separately approved design.

## Deploy from GitHub Actions

The `Deploy AurisCore to Vercel` workflow targets the existing
`auriscore-cloud` and `auriscore-inference` projects. Pull requests to
`master` run **Verify WebApp, gateway and model** without production
credentials. Require this check in the branch ruleset to prevent merges
with pending or failed checks. A push to `master` reruns the checks before
deploying both projects. To deploy manually, open GitHub
Actions, select the workflow, choose `master`, then choose `both`,
`website`, or `inference`. Use `both` if a backend change needs a matching
WebApp parser. Use `inference` for a compatible model-only update.

One-time setup in GitHub Settings → Environments → `production`:
add the environment secret `VERCEL_TOKEN` using a Vercel access token scoped to
`rain-frogs-projects` with production deployment permission. Also add
`AURISCORE_INFERENCE_TOKEN` with the same bearer credential used by the two
Vercel projects. The workflow requires both before deploying. Restrict the
environment's deployment branches to `master`. Collaborators with repository
write access can run the workflow using the saved secret. The public project
and team IDs are in the workflow. Redis, pairing secrets and inference
configuration are already managed in the existing Vercel projects.

The check runs TypeScript, WebApp analysis tests with disposable TCP Redis,
the device-gateway tests, a cloud-mode build, and HTTP requests against the
staged Python function. The smoke script runs L030 (Lung), A105 (Abdomen),
and H022 fold 1 (Heart Murmur) on per-organ synthetic audio as PCM and WAV.
It checks model identity and output agreement and confirms silence is rejected.
After deployment the workflow checks public WebApp reachability and anonymous
denials, then repeats authenticated inference against the production Python
function. The production check also downloads the reference WAV from the
website, verifies its SHA-256, and runs it through H022. The workflow sets the
production inference hostname on the WebApp and supplies the same GitHub
environment secret to both Vercel deployments and the smoke test. Its logs
include model versions, Lung and Murmur scores, and Abdomen
candidate counts and thresholds. Each deployment carries the source SHA in
`sourceCommit` metadata.
A failed production smoke marks the run failed for operator investigation.
These checks complement browser/account, physical acquisition, and optional
HTTPS Redis relay checks.

The workflow enables the staged L030 and A105 engineering models and downloads
[H022 fold 1 from GitHub Releases](https://github.com/vinend/Despro-AurisCore/releases/tag/heart-research-model-h022).
The release contains an encoder, normalization and logistic head derived from
CirCor DigiScope by Oliveira et al., available under ODC Attribution 1.0.
The staging script verifies the pinned archive hash and all three asset hashes
and carries the release license and engineering scope into the bundle. To stage
it manually, pass `--heart-bundle` and `--heart-bundle-sha256`. A website-only
run checks the existing production inference backend.

## Provision the Vercel projects

1. Create a FastAPI project for analysis. From the repository root, with the
   pinned `librosa` version from `hosting/requirements.txt` installed, run
   `python scripts/prepare_vercel_inference.py`. Deploy the resulting
   `.runtime/vercel-inference` directory as that project's root, for example by
   running `vercel` inside it. To regenerate, first move the previous staging
   directory aside. The script stages the tracked L030 assets and runtime
   sources without datasets or experiment outputs beyond those model assets.
   It also stages the import stubs that librosa needs at runtime and Vercel
   strips from installed dependencies. Use `--output` to stage in a fresh directory.
2. Enable Fluid Compute and Active CPU on the Python project. Set
   `VERCEL_SUPPORT_LARGE_FUNCTIONS=1` for the TensorFlow dependencies and
   `AURISCORE_LUNG_ENGINEERING_L030=1` to select the staged Lung model. Set
   `AURISCORE_INFERENCE_TOKEN` to a fresh secret. Leave
   `VERCEL_ANALYZE_BUILD_OUTPUT` disabled on the actual TensorFlow deployment.
   The size diagnostic applies the standard limit and can fail an otherwise
   eligible Large Functions build. Verify that the deployed model cold-starts
   within the configured 60-second function duration.
3. Create a Next.js project with `WebApp` as its root and Fluid Compute
   enabled. Use a native TLS Redis service reachable from Vercel that supports
   `SUBSCRIBE`, `PUBLISH`, and Lua `EVAL`. Place Redis and the gateway in the
   same region. Use a dedicated Redis database or a distinct namespace per
   deployment; the gateway supports one active device and one browser per
   namespace. Set the following before building this project.

| WebApp variable | Value |
| --- | --- |
| `NEXT_PUBLIC_AURISCORE_CLOUD` | `1`, selects the cloud gateway and supplies the operator credential on analysis calls |
| `AURISCORE_CLOUD_ANALYSIS` | `1`, selects HTTP inference |
| `AURISCORE_REDIS_URL` | Native `rediss://` connection string |
| `AURISCORE_CLOUD_NAMESPACE` | Unique letters, digits, underscores or hyphens |
| `AURISCORE_BROWSER_ORIGIN` | Exact HTTPS origin of this WebApp, without a trailing slash |
| `AURISCORE_DEVICE_TOKEN` | Device-only secret entered during ESP32 setup |
| `AURISCORE_OPERATOR_TOKEN` | Separate secret entered into the browser pairing form |
| `AURISCORE_INFERENCE_URL` | Base HTTPS URL of the Python project |
| `AURISCORE_INFERENCE_TOKEN` | The same server-to-server secret configured on the Python project |

Generate different random secrets for each role, for example 32 random bytes
encoded as hex. Set them as server-side project variables. The ESP32 needs an
HTTPS hostname whose deployment protection allows the WSS upgrade before
application pairing. The WebApp needs to be able to reach Python before
application bearer authentication. Configure Vercel deployment protection
accordingly for these engineering endpoints.

The staged service includes Heart DSP, H022 engineering Murmur when the release
archive is supplied, opt-in L030 Lung clip candidates, and
opt-in A105 Abdomen event candidates (`AURISCORE_ABDOMEN_ENGINEERING_A105=1`).
A105 uses the tracked weights and exported training normalization vectors.
The WebApp must support the versioned candidate interval fields before enabling
A105. An explicitly selected verified Heart package takes priority over H022.

## Prepare the ESP32

Use the ESP32 3.3.12 core and Arduino WebSockets 2.7.2. Obtain the public root CA
certificate for the actual gateway hostname from its CA and save it as a PEM
file. From the repository root, run:

```powershell
.\scripts\build_wifi_firmware.ps1 -CloudRootCa C:\path\to\gateway-roots.pem
```

Flash the resulting cloud build using the ESP32 board settings in the firmware
guide. In the ESP32 setup portal, enter `wss://your-webapp.example` as the
gateway and enter the device token. The firmware obtains time via SNTP and
validates the server certificate before sending the pairing token. It connects
to port 443 at `/api/gateway/device`. The same build accepts a plain LAN host
for the existing port 8082 and `/device` path, using the separate LAN token.

Open the HTTPS WebApp and enter the operator token. The page uses
`/api/gateway/browser` and starts capture when the device announces itself.
The Redis relay is live-only. Dropped audio invalidates the current capture.
WebSocket lifetimes are bounded by the Vercel function duration. A reconnect
starts a new capture, including after a deploy. Cloud multipart WAV uploads
have a 4 MiB audio limit.

## Acceptance

- Run `npm run typecheck` and `npm run test:analysis` in `WebApp` with the
  existing `AURISCORE_PYTHON` configured. Set `AURISCORE_TEST_REDIS_URL` to an
  isolated Redis instance to include the two-listener gateway integration test.
- Verify with the physical ESP32 and browser on different networks. Pair each
  with its own credential, record at least 30 seconds of synthetic Lung audio,
  and confirm a versioned L030 result for both live PCM and recorded WAV.
- Repeat with invalid credentials, a second browser, a wrong trust root, a
  device power cycle and a gateway reconnect. Confirm that a gap discards the
  interrupted window and that a new capture works.
- Measure cold and warm inference latency and Redis command usage during capture.

Platform references: [WebSockets on Vercel](https://vercel.com/kb/guide/real-time-chat-websockets),
[Python runtime](https://vercel.com/docs/functions/runtimes/python),
and [Large Functions](https://vercel.com/docs/functions/limitations#large-functions).
