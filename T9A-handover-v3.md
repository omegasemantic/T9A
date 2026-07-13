# T9A / T9AMAIL — Project Handover (v3, consolidated)

This supersedes both the original handover and handover v2 — merged
into one current document. Historical detail that's no longer accurate
(e.g. a `merger.sh` step that turned out to be unnecessary, an SMTP-based
send plan later replaced) has been folded in or dropped rather than kept
as a separate trail; see "Superseded/rejected approaches" at the end for
anything worth remembering *why* it didn't happen.

## Goal
Enable email read/reply functionality on an HMD feature phone (2.4" screen)
via Opera Mini Extreme. Opera Extreme strips pages to plain text/basic HTML —
no JS, minimal CSS, single-column only. All mail processing happens
server-side (VPS); the phone only ever fetches simple rendered HTML pages.

## Wider project context
T9AMAIL is one module of a broader **T9A** project (an experiment in
running useful services on the HMD feature phone to ease the practical
gap from an iPhone). A second module, **T9AMAPS** (directions/geocoding,
formerly a standalone project called `gmap`), already exists as working
code. It has been folder-scaffolded (`T9A/maps/`) but not yet migrated in
— still pending, low priority relative to mail.

## Architecture principle
Avoid live IMAP calls at the web-serving stage entirely. `mbsync` handles
sync, and everything downstream operates on local files only — fast,
inspectable, no protocol round-trips while a user is waiting on a page
load.

## Two-module split (deliberate, not accidental)
- **View Module** — read-only. Pages the mailbox, lets the user browse,
  displays a selected message. No send awareness.
- **Compose Module** — construct + send a reply. `mail.raw` is the sole
  bridge between the two; deliberately no shared code across that
  boundary (field-extraction logic may be duplicated on the Compose
  side rather than reused from View, since the two have different
  correctness requirements).

## Working chain (View Module) — proven end to end, on both `penguin`
and the VPS
```
mbsync posteo   → syncs Posteo IMAP into ~/Mail/INBOX/{new,cur}
pager.sh        → scans mailbox, writes headers.txt (UID, read status,
                  From, Subject, Date, Warning flag)
browser.sh      → interactive one-at-a-time viewer/menu:
                  [n]ext [p]revious [v]iew [r]eply [q]uit
                  - view: decodes + displays body, writes mail.raw
                  - reply: writes mail.raw, hands off (stub only)
chooser.sh      → older list-style alternative to browser.sh (still
                  present, not needed going forward — browser.sh is the
                  current, working UI)
tmail.sh        → wrapper: mbsync → pager → browser → rawmail2md
```
No `merger.sh`/merge step exists or is needed — an earlier debugging
detour explored merging `new/`+`cur/` into one directory to chase what
turned out to be a display-only bug (see Bugs, below); the real fix
was simpler and no merge step was ever required in the working chain.

## Shared helper library — `mail_helpers.sh`
Sourced (not executed) by `pager.sh` / `browser.sh` / `rawmail2md.sh`.
Contains:
- `clean_from` — strips `<email>` brackets, prefers display name, falls
  back to bare address if no display name exists.
- `decode_subject` — RFC 2047 decode (`=?utf-8?Q?...?=` etc.), via python3.
- `trim_date` — reformats RFC 5322 dates for display, **now converts to
  local time** (see Timezone fix, below) — previously just parsed and
  displayed the sender's original offset verbatim, which was a real,
  confirmed-visible bug (a message sent ~30 min prior displayed as "13
  hours ago"). Uses Python's `email.utils.parsedate_to_datetime` +
  `zoneinfo`, deliberately **not** the `date -d` shell command (an
  earlier, separate bug: `date -d` silently used the container's local
  timezone in an uncontrolled way and occasionally shifted messages to
  the wrong calendar day — don't revert to it).

Rationale for a shared library: within the View module, field-cleaning
rules (from/subject/date) are genuinely shared logic, not incidental
duplication. This does NOT extend across the View/Compose boundary by
design.

## Timezone fix — implemented
`trim_date` now:
1. Parses the message's original `Date:` header (unchanged).
2. **Converts to a configurable local timezone** read from
   `$HOME/.t9arc`'s `timezone` value (see Project file philosophy,
   below), via Python's `zoneinfo` module — correctly handles NZ
   daylight saving automatically, no hardcoded fixed offset.
3. Formats as `%-d %b %Y, %H:%M` — **24-hour HH:MM, project-wide
   convention, decided explicitly** (no am/pm anywhere in the project
   going forward).
Falls back to `Pacific/Auckland` if `.t9arc` or the `timezone` variable
is missing, so the function is safe to call even before `.t9arc` exists.

## Filter 1 vs Filter 2 (content-safety/warning model) — unchanged,
still accurate
- **Filter 1** (in `pager.sh`) — cheap, advisory, per-message, runs
  across the whole mailbox every time. Checks `Content-Type:` header;
  flags anything not plain `text/plain` (or missing the header) with
  `Warning: !` in headers.txt. Not mission-critical.
- **Filter 2** (in `rawmail2md.sh` / `browser.sh`'s `render_body()`) —
  heavier processing on the single selected `mail.raw`. Handles
  quoted-printable decoding (python3 `quopri`) and crude HTML tag
  stripping. Does **NOT** yet handle base64-encoded bodies or genuine
  `multipart/alternative` MIME messages (a `text/plain` part alongside
  `text/html`; correct behaviour would prefer the plain part). **Still
  a known, real, unbuilt gap.**

## Bugs found and fixed (this build cycle)
- **`rawmail2md.sh` had a large duplicated block** (identical body
  extraction/decode/write logic appearing twice in sequence, harmless
  in output but wasteful — the live `echo "Wrote $OUT"` was only in the
  second copy). Deduplicated; confirmed working against a real message
  including quoted-printable decoding.
- **`browser.sh`'s `generate_raw` was non-functional**: `MAILDIRS` was
  commented out (a leftover from an earlier debugging detour into a
  `merged/` directory approach — see below) and `TMPFILE` was never
  defined. `[v]iew`/`[r]eply` silently could not work. Fixed:
  `MAILDIRS` restored to `("$HOME/Mail/INBOX/cur" "$HOME/Mail/INBOX/new")`
  (matching `pager.sh`); `TMPFILE` defined as `"$SCRIPT_DIR/mail.raw"`.
  Confirmed working end to end.
- **The original "unread showing at wrong end of the list" confusion**
  was **not** a script bug — confirmed to be user error (not scrolling
  to the end of the list; `browser.sh` deliberately starts at the
  highest array index = most recent). The `MAILDIRS` order in
  `pager.sh` (`cur` first, `new`/unread appended last) is correct and
  intentional given `browser.sh` starts from the end of the array — the
  two scripts' ordering assumptions are coupled by design. Worth a code
  comment noting this coupling so a future edit to either script
  doesn't break it unknowingly.
- **Unread indicator added**: `browser.sh` now parses the `| read` /
  `| unread` suffix on each `UID:` line (previously parsed but
  discarded) into a `statuses` array, displaying a compact `(N)` next
  to unread UIDs. No `pager.sh` changes needed — it already emitted
  this. **Deliberately left without any backing "mark as read" logic —
  see Read-flag sync, below.**

## Read-flag ("mark as read") sync — investigated, deliberately deferred
Considered implementing proper Maildir `:2,S` flag-setting (rename +
move on `[v]iew`, relying on `mbsync`'s genuine bidirectional sync to
propagate the read-state back to Posteo) specifically because of a
concrete scenario: fast threaded exchanges (e.g. "what time dinner? /
8 works? / can't make it") where reading on the phone but not marking
read anywhere would mean re-scanning the same thread later on a primary
device. A naive "just move the file to `cur/`" approach was assessed
(not empirically tested) as likely insufficient, since Maildir encodes
read-state in both folder location *and* a filename flag suffix — a
plain move would likely be invisible to mbsync's change-detection and
get silently reverted on next sync.

**Decision: not being implemented for now.** The phone is confirmed to
be a fallback device only — the user's primary mail triage happens on a
real client, where catching "already read" mail is trivial. The `(N)`
indicator remains purely a passive display of whatever `pager.sh`
currently reports from the server, with no local or server-side
write-back. This is a deliberate scope decision, not an oversight — if
revisited later, the `:2,S`-suffix approach above is the correct
direction, not a local-only ledger.

## Sending mail — solved via Resend (HTTPS), not SMTP
### Why SMTP was abandoned
The VPS host (Tierhive) blocks outbound ports 587/465 by default,
allowlisting only a short list of named commercial relays (Amazon SES,
Mail Baby, Mailgun, Mailjet, Mandrill, Resend, Sendgrid). Confirmed via
direct `nc` testing that this is a general policy, not Posteo-specific
— Gmail's SMTP was also tested and found equally blocked. A whitelist
request for Posteo specifically was sent to Tierhive support (ticket
#621) and may still be open, but is no longer load-bearing — see below.
`msmtp`/`.msmtprc` remain correctly configured and were confirmed
*functionally* fine (config loads, TLS negotiates, password populated)
— the sole blocker was the network-level port restriction, unrelated to
msmtp itself.

### The chosen solution: Resend
Resend uses a plain HTTPS API call (port 443, already open) rather than
SMTP, sidestepping the port restriction entirely. Setup completed and
**tested working end-to-end, multiple times, including via the final
script**:
- Domain `omegasemantic.org` (bare root domain, deliberately not the
  `map.` subdomain, to keep sending identity separate from the website)
  verified with Resend via three DNS records added at Porkbun: DKIM TXT
  (`resend._domainkey`), SPF TXT and MX (both scoped to
  `send.omegasemantic.org`, confirmed **not** to conflict with the
  domain's pre-existing Porkbun email forwarding — see next point).
  Resend's "enable receiving" toggle deliberately left off.
- **A pre-existing Porkbun email forward was discovered mid-session:
  `hello@omegasemantic.org` already forwards to
  `simon.kearns@posteo.net`, and was confirmed working.** This settled
  what the outgoing sender/reply address should be — `hello@
  omegasemantic.org` is used as the Resend "from" address, so genuine
  replies land in the real Posteo inbox automatically. No "do not
  reply" disclaimer footer needed after all.
- API key generated in Resend's dashboard, stored in
  **`$HOME/.resendrc`** as `RESEND_API_KEY=...` (same convention as
  `.msmtprc` — see Project file philosophy, below).
- **`send.sh` built and working** — a standalone, parameterized script
  (`./send.sh <to> <subject> <body>`), correctly sources
  `$HOME/.resendrc`, checks the key is actually populated before
  attempting a send (fails loudly rather than silently if sourcing
  ever breaks again), and POSTs to Resend's API. **Confirmed working
  via a real test send, received in the real Posteo inbox.**

### What replaces the original SMTP-based Compose Module plan
The original plan (`msmtp -t < reply.rfc`) is superseded for the "send
from VPS" leg. The RFC 5322 header-construction logic (`To`,
`Subject: Re: ...`, `In-Reply-To`, `References`, extracted from
`mail.raw`) is still needed conceptually and not yet built — only the
final delivery hop changes, from a raw SMTP pipe to a `curl`/HTTP POST
via `send.sh` (or an equivalent direct-from-Python call, since Resend's
API is plain HTTPS — worth deciding which when the Compose Module is
actually built).

## Project file philosophy — where things live and why
A deliberate three-way split, worth keeping consistent as the project
grows beyond just mail:

- **`$HOME` dotfiles — secrets and project-wide config, "system app"
  style.** `.msmtprc`, `.resendrc`, and **`.t9arc`** all live in `$HOME`
  on both `penguin` and the VPS, deliberately outside git. One place to
  look, one deploy mechanism: `scp ~/.msmtprc ~/.resendrc ~/.t9arc
  root@sally:/root/` moves all of it in one line.
- **`.t9arc` — project-wide, non-secret, human-edited context.** Plain
  `key=value` shell syntax (`source`-able directly by bash, trivially
  parseable by Python via a short loop), `#`-comments allowed, no
  YAML-style indentation-sensitivity. Chosen deliberately over JSON/YAML
  for this one file because the driving use case is a fast, low-risk,
  comment-friendly edit while literally travelling (e.g. Wellington →
  Melbourne: one line change, `timezone=Australia/Melbourne`). Current
  contents: `location`, `timezone`, `transit_mode` — genuinely shared
  context both `mail` and `maps` need, where module-local duplicates
  would risk drift (e.g. mail's timezone still saying Wellington after
  a trip, because only maps' city got updated).
- **Module-local `.json` — runtime/working state, not config.**
  `maps/gmap.json` (`_START`, `_DES`, place IDs, etc.) is the working
  state of the last/next API call — changes far more often than
  `.t9arc`, written to as much as read, meaningless to other modules.
  JSON kept here deliberately (not switched to `.t9arc`'s format)
  because this data is genuinely structured/nested and
  machine-written more than hand-edited — opposite profile from
  `.t9arc`. Any future mail-side equivalent should follow the same
  pattern: local to `mail/`, JSON, not treated as "config."
- **Git repo (`github.com/omegasemantic/T9A`) — code only.** Scripts,
  `app.py`, static assets. Never secrets, never `.t9arc`, never
  generated/runtime files. `.gitignore` excludes: `venv/`,
  `__pycache__/`, `*.pyc`, `headers.txt`, `mail.raw`, `body.md`, `*.log`.
  `penguin` is the source of truth for code; the VPS deploys via
  `git pull`. Repo history was force-reset this cycle (old, stale
  commits replaced with the current consolidated state — old versions
  still exist locally if ever needed, nothing was actually lost).

## VPS deployment — working, and now has a matching local dev loop
### Architecture (as actually provisioned)
- VPS provider: Tierhive (low-cost tier). Domain: **omegasemantic.org**,
  web-facing subdomain **map.omegasemantic.org**. Tierhive fronts all
  IPv4 traffic through their own regional HAProxy (Sydney, AU) — no
  user-facing haproxy config needed on the VPS itself.
- The VPS has **no separate personal user account** — confirmed (not
  assumed) that all work happens as root. Given this, and given the
  user has explicitly and knowingly deprioritised security hardening
  for this project, the app **runs as root** too (a `t9amail`
  low-privilege user was created, tested, then deliberately removed
  once this was decided — not an oversight if you don't find a trace
  of it).
- Bottle binds directly to `0.0.0.0:80` — no reverse proxy, no iptables
  redirect (an iptables port-80→8080 redirect was set up, then
  deliberately removed once root-direct-bind was chosen instead).
  Matches the pattern already proven by the older, separate `gmap`
  project's `server.py` (also root, also binds 80 directly, also
  explicitly serves `/`).
- Running as a systemd service (`t9amail-web.service`), `User=root`,
  auto-restarts on failure, starts on boot.

### File layout (current, both machines, now aligned)
```
T9A/
    .gitignore
    handover (this file's predecessor, kept for history)
    handover_2 (superseded by this v3)
    mail/
        app.py
        browser.sh
        chooser.sh
        mail_helpers.sh
        pager.sh
        rawmail2md.sh
        README
        send.sh
        static/hello.html
        test.sh
        tmail.sh
        venv/          (gitignored, regenerate with pip install bottle)
    maps/              (scaffolded, gmap migration still pending)
```
On the VPS: `/root/T9A/...`, same structure, pulled via `git clone`/
`git pull` rather than hand-typed. `venv/` is regenerated locally on
each machine (`python3 -m venv venv && pip install bottle`), never
transferred.

### Local dev loop — now working, matches VPS exactly
`penguin` had a default/unused nginx (Crostini container default,
confirmed via `curl`/config inspection to be genuinely just the stock
"Welcome to nginx" page with nothing depending on it) squatting on port
80, which was removed (`apt remove --purge nginx nginx-common`) to free
the port. `app.py` now runs identically on both machines with **zero
divergence** — same file, same port 80, same command:
```
sudo <path-to-venv>/bin/python3 app.py
```
(the explicit `sudo <venv-path>/bin/python3` form matters — bare
`sudo python3` can silently fall back to the system Python and lose the
venv's installed packages, since `sudo` resets `PATH` by default)

Deliberately **not** turned into a local systemd service — the VPS
needs always-on; `penguin` is an on-demand test sandbox, run manually
and Ctrl-C'd when done. Making it persistent locally would just mean it
permanently squats on port 80 whether being used or not, for no benefit.

### Known Tierhive-specific gotchas (worth remembering if this recurs
or if ever migrating providers)
- **Backend health checks require the app to answer `/`, not just a
  named file.** This was the actual root cause of a "backend shows
  Unhealthy, 503 from outside" problem that consumed real debugging
  time — `/hello.html` alone wasn't enough. Re-saving the backend
  config in Tierhive's console (Configure Backends → re-submit) also
  appears to force an immediate re-check rather than waiting for the
  next scheduled cycle.
- **Outbound mail ports are default-blocked** — see Sending, above.
- Confirmed via `iptables -L` and `ufw status` that nothing on the VPS
  itself was ever blocking outbound traffic — the restriction is
  entirely at Tierhive's network edge.

## Compose Module — status
Still the next major build. Send-delivery mechanism is now proven
(`send.sh` via Resend); RFC 5322 header-construction logic
(`To`/`Subject: Re: .../In-Reply-To`/`References`, extracted from
`mail.raw`) is not yet written. Minimum required fields, per RFC 5322:
`To`, blank line, body — `Subject` almost always wanted;
`In-Reply-To`/`References` needed for proper threading in the
recipient's client.

## Superseded/rejected approaches (kept for context, not to be
re-attempted without a new reason)
- **`merger.sh`** (flattening `new/`+`cur/` into one dir) — explored
  while chasing what turned out to be a display bug (not scrolling to
  the list's end in `browser.sh`), not actually needed in the working
  chain.
- **SMTP-based sending** (direct via Posteo, or via a Gmail relay) —
  blocked at the network level by the VPS host regardless of provider;
  replaced by Resend's HTTPS-based API.
- **Local-only "mark as read"** (plain folder move, no Maildir flag
  suffix) — assessed as likely to be silently reverted by mbsync's next
  sync; rejected in favour of either doing it properly (`:2,S` suffix)
  or not at all. Currently: not at all (see Read-flag sync, above).
- **A dedicated non-root `t9amail` VPS user + iptables redirect** — both
  built, tested, then deliberately removed once it was confirmed the
  VPS has no other user anyway and security hardening isn't a stated
  priority for this project.
- **JSON or YAML for `.t9arc`** — considered, rejected in favour of
  plain `.bashrc`-style syntax specifically for fast/low-risk editing
  while travelling; see Project file philosophy, above.

## Immediate next steps (revised priority order)
1. Build the Compose Module: RFC 5322 header construction from
   `mail.raw`, wired to `send.sh` (or an equivalent direct-Python
   Resend call).
2. Migrate `gmap` into `T9A/maps/` (folder scaffolded, not yet
   populated — deliberately deferred, lower priority than mail).
3. Handle genuine `multipart/alternative` MIME messages properly in
   Filter 2 (still an open, known gap).
4. Wire the View Module's bash scripts into Bottle routes generally
   (UID travelling via URL params, replacing `read -p` prompts with
   HTTP routes/links — the mechanism was proven this cycle via
   `test.sh`'s `subprocess` call from `/test`, not yet applied to the
   real mail scripts).
5. Test on the real feature phone via Opera Mini Extreme specifically
   (not just desktop browser) — periodic real-device checks, not just
   at the end, remains the agreed cadence.
6. Eventually move `mbsync` + cron onto the VPS, so sync doesn't depend
   on `penguin` being awake/online.

## User context (do not need to re-derive, but don't over-reference)
Comfortable with vim, bash, ChromeOS/Crostini (Linux container), has an
existing Jekyll site on GitHub. Has, over the course of this build,
also become comfortable with: systemd service files, iptables basics,
DNS record management (Porkbun), git/GitHub workflow (force-pushed a
consolidated history to `github.com/omegasemantic/T9A`), and the
general shape of Maildir/IMAP sync semantics — worth assuming this
baseline going forward rather than re-explaining from scratch. Has
explicitly and knowingly deprioritised security hardening for this
project (root-only operation, accepted trade-off) — considered choice,
not to be re-litigated unprompted. Has also explicitly ruled out
chasing commercial "hobbyist-tier" bulk-email APIs generally (prior bad
experience on the maps/Twilio-adjacent project) — Resend was accepted
specifically because it was already on Tierhive's whitelist and solved
a concrete blocker, not as an endorsement of that category of service
generally. Storage/dotfile convention: "check `$HOME` first" for
anything credential- or config-like, deliberately mirroring how real
system tools (`msmtp`) already behave. Prefers working incrementally
with real inspectable files at each stage over black-box tooling.
