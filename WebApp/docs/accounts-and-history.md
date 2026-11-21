# Accounts and saved recordings

Login failures now give separate guidance for incorrect credentials,
unconfirmed email, provider email restrictions and connectivity/rate limits.
Only an unconfirmed-email response exposes the user-initiated confirmation
resend action. It requests the existing signup confirmation and does not
confirm the account itself. Provider email limits and SMTP requirements remain.

The deployed WebApp uses the dedicated Supabase project `AurisCore`
(`eillyzplrheparplfikw`) in Singapore, in the same organization as Netlab CTF.
The CTF project remains independent. Supabase Auth stores credentials and email.
The initial screen presents login and an explicit guest option before mounting
the examination workspace. Existing signed-in sessions enter the workspace.
The profile icon in the workspace header opens a menu containing
Settings and Keluar. The Settings item links to `/settings`, which edits name, date of birth, gender
and Auth email. Email changes use `auth.updateUser` and remain subject to
provider confirmation. Settings profile fields use a single-column layout at
all viewport widths. Saving profile fields does not require an email change.
The account menu is unavailable during active recording/analysis. Profile
fields stay editable after saving; the card has no separate edit/logout buttons.
Keluar ends the current browser Auth session and returns to the initial screen.
Guest sessions can open Settings, with Keluar disabled. Navigating
away ends the current workspace and its transient guest history.
The profile table stores name, date of birth and gender. The session table
stores the existing analysis envelope and immutable WAV identity.

The private `auriscore-recordings` bucket allows an authenticated owner to
read objects under their user UUID. Uploads must match an existing owned
session. Anonymous requests have no table access. The browser uses the
publishable key and its user's session, with no service-role key.

Configure `NEXT_PUBLIC_SUPABASE_URL` and
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` on the WebApp project before building.
In Supabase Auth URL Configuration set the Site URL to
`https://auriscore-cloud.vercel.app` and allow
`https://auriscore-cloud.vercel.app/**` for confirmation and recovery links.
The owner confirmed these Auth URL settings were saved on 2026-11-18.
Use Supabase's email provider settings to configure delivery for the team's
actual users. Supabase's default email service has recipient and sending-rate
restrictions. A custom SMTP provider is needed for general signup and recovery
delivery. Signup requires email confirmation. Accounts created for acceptance
were generated fixtures confirmed through the test setup; those tests do not
prove external email delivery.

The schema is defined in
`supabase/migrations/20261117171357_auriscore_accounts_and_sessions.sql`.
It was applied to the dedicated project using the connected management tool.
For a new project apply the migration once and verify RLS before enabling
accounts in its deployment.

A signed-in capture is queued in IndexedDB under the account that started it.
The session row is inserted before the private WAV upload. The ready-state
update requires the object to exist. Retrying an interrupted upload uses the
same UUID and verifies a pre-existing WAV's size and SHA-256 before finalizing.
Pending local files are removed only after cloud completion. Local data may
remain pending after sign-out and resumes when the original user returns.
Concurrent save/online requests are serialized and trigger a fresh outbox scan
after the current upload; the latest account's request is retained.
The UI clears the prior account's transient results when accounts change.

History pages contain 30 sessions at a time. Selecting a session displays
its saved result and downloads the private WAV into an object URL for the
audio player. The URL is revoked when the details close or the account changes.
Reloading or signing in on another phone retrieves the same cloud records.

Verify changes with the session repository regression tests and two generated
test accounts. Check cross-account SELECT/INSERT/UPDATE/object access denial,
duplicate-save retries, upload recovery, byte-identical WAV download and a
fresh login retrieving existing history. Use synthetic recordings and remove
the generated test accounts and objects after acceptance.
