# Account Integrations — Design & Setup Plan

> Status: **PLAN ONLY — not built.** Connect the user's Gmail / Calendar / LinkedIn so
> discovery → outreach → follow-up → publishing all happen inside the app.
> Date: 2026-06-17. See also [[talentrupt-marketing-agent-rebuild]] / BUILD_PLAN.md.

---

## 0. Shared integration framework (build once)

All connections share the same plumbing:

- **`connections` table**: `id, provider, account_email, access_token (encrypted), refresh_token
  (encrypted), scopes, expires_at, status, created_at`. Tokens encrypted at rest (Fernet/AES key
  in `backend/.env`, never committed).
- **OAuth flow**: a **Settings → Integrations** page with "Connect" buttons → provider OAuth popup →
  `/api/integrations/{provider}/callback` exchanges the code, stores tokens.
- **Token refresh**: middleware refreshes expired access tokens via the refresh token.
- **Provider adapters**: `integrations/gmail.py`, `calendar.py`, `linkedin.py` behind a common
  interface so the rest of the app calls `send_email()`, `create_event()`, `publish_post()`.
- **Secrets** (client id/secret per provider) live in `backend/.env`.
- **Tenancy**: single-org "internal" first (simplest auth); multi-tenant later.

---

## 1. Gmail — send outreach + reply sync ✅ (recommended first)

**Setup (one-time):**
- Google Cloud project → enable **Gmail API** → OAuth consent screen.
  - Single team on Google Workspace → mark app **"Internal"** (skips Google's verification review).
  - External/personal Gmail → needs Google app **verification** for sensitive scopes.
- OAuth client (Web) → client id/secret → `backend/.env`.
- Scopes: `gmail.send` (send) + `gmail.readonly` or `gmail.modify` (detect replies).

**What it unlocks:**
- Send the generated outreach **from the user's own inbox** (`users.messages.send`).
- Store the sent thread id on the `Opportunity`.
- **Reply detection**: poll the thread (or Gmail push via Pub/Sub `watch`) → on inbound reply,
  auto-advance pipeline **Contacted → Replied** and surface the reply in-app.

**Constraints / risks:**
- Sending limits: personal Gmail ~**500/day**, Workspace ~**2,000/day**.
- Cold-email deliverability: needs SPF/DKIM/DMARC, warmup, low volume, real personalization —
  otherwise spam folder or account flags.
- For higher volume + better deliverability, alternative = **transactional provider**
  (SendGrid / Amazon SES / Postmark) sending from a domain (not the personal inbox). Trade-off:
  not "from their Gmail," but safer at scale.

---

## 2. Google Calendar — real follow-ups ✅

- Same Google project → enable **Calendar API** → scope `calendar.events`.
- When a follow-up `CalendarTask` is created (or a meeting booked), create a real calendar event.
- Optional two-way sync later.

---

## 3. LinkedIn — Company Page publishing ✅

- LinkedIn **Developer app** → request **Community Management API** access (approval required) →
  page **admin authorizes**.
- Scopes: `w_organization_social` (post), `r_organization_social` (read).
- Publish generated post text + image to the **Talentrupt company page** (Posts/ugcPosts API);
  schedule via the app calendar. Closes the loop on the content/campaign side.
- Note: LinkedIn app review/approval can take time.

---

## 4. Outlook / Microsoft 365 (alternative to Gmail)

- Microsoft Graph → scopes `Mail.Send`, `Mail.Read`. Same pattern as Gmail for Outlook users.

---

## 5. LinkedIn person-to-person outreach (DMs / connection requests) ⚠️ HIGH RISK

> User asked to explore automation anyway. Here is the honest landscape. **I will not implement
> any of this without explicit, written go-ahead** acknowledging the risks below.

**There is NO official API** for sending connections or DMs. Every automation path violates
LinkedIn's User Agreement to some degree. Options, worst-to-least maintenance:

| Option | How | Risk |
|---|---|---|
| **A. Assisted (no automation)** | App drafts the message + opens the prospect's profile; user clicks Send | **None.** ToS-compliant. Recommended default. |
| **B. Third-party automation tool** (HeyReach, Expandi, Dripify, PhantomBuster, Waalaxy, LaGrowthMachine) | App hands the drafted message + prospect to the tool's API; the tool runs the automation through the user's LinkedIn session | Violates LinkedIn ToS; tools are **built for this** and manage rate-limits/warmup, but accounts **still get restricted/banned**. |
| **C. In-house browser automation** (Playwright / unofficial "Voyager" API / `linkedin-api`) | We drive a logged-in session directly | **Highest** ban risk + constant breakage as LinkedIn changes; heavy maintenance. Not recommended. |

**Hard truths regardless of tool:**
- LinkedIn detects automation via behavioral patterns. "Safe" caps are roughly **~20-25 connection
  requests/day** and **~100-200 invites/week**; exceeding them triggers restrictions.
- Bans can be **permanent** and there's no appeal guarantee.
- Legal gray area (LinkedIn has pursued scrapers).

**If you want automation, the least-bad path = Option B with safeguards:**
- Integrate a reputable tool (e.g., HeyReach/Expandi) **via its API** — the app orchestrates
  (who + what message), the tool absorbs the risky execution and the detection-evasion engineering.
- Use a **dedicated LinkedIn outreach account** (Sales Navigator), **never the founder's primary**.
- Warm the account up; keep volumes conservative; rotate; human-like timing.
- Explicit in-app consent that this is the user's own risk.

**Recommendation:** ship **A (assisted)** now; offer **B (tool integration)** as an opt-in later
with the safeguards above. Skip C entirely.

---

## 6. Phasing

1. **Integration framework** (connections table, OAuth scaffold, Settings → Integrations UI, token encryption).
2. **Gmail** send + reply-sync → pipeline auto-updates.
3. **Google Calendar** → follow-ups become real events.
4. **LinkedIn company-page publishing**.
5. **LinkedIn DMs**: assisted now; optional third-party-tool integration (opt-in, safeguarded) later.
6. (Optional) CRM sync (HubSpot/Salesforce), Outlook.

## 7. Setup checklist (user actions required)
- [ ] Google Cloud project + OAuth client (Gmail + Calendar) → client id/secret to `backend/.env`.
- [ ] Decide email mode: personal Gmail / Workspace / transactional provider (SendGrid/SES).
- [ ] LinkedIn Developer app + Community Management API access + page admin consent.
- [ ] (If automating DMs) choose a dedicated LinkedIn account + pick a third-party tool + accept risk.
- [ ] Decide single-org internal vs multi-tenant (affects Google verification).

## 8. Open decisions
- Email: personal-inbox (Gmail/Graph) vs domain-based transactional provider vs both?
- Internal-only app vs multi-tenant SaaS (changes the OAuth verification burden).
- Which CRM, if any.
- LinkedIn DM automation: assisted-only vs third-party tool integration.
