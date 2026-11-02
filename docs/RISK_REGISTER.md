# Prioritised risk register

2 November 2026. Likelihood is qualitative; production configuration has not
been inspected. No monetary penalty estimates or promises of immunity.

| ID / severity | Finding, evidence and potential impact | Likelihood / obligation | Implementation status | Remaining owner action / residual risk |
|---|---|---|---|---|
| S1 High conditional | Known default session secret allowed impersonation if production omitted SECRET_KEY; app config/auth trust boundary | Exploitable if unsafe config used; unknown live state. Confidentiality/integrity obligations | Fail-closed startup implemented; no secret rotated | Confirm private stable secret/HTTPS before deployment; invalidating compromised sessions may require planned rotation |
| S2 Medium | GA previously loaded before choice; shared header | Confirmed source behaviour; PECR/UK GDPR processing conditions | Opt-in/reject/withdraw implemented | Verify GA Admin, children's processing, contracts/transfers and live request behaviour |
| S3 Medium accepted | Offline answers permit self-score inflation; offline package/guess routes | Easy; integrity and future consumer/prize risk | Explicitly accepted by owner for no-prize play | Reassess before prizes/paid entry. No claim of cheat-proof competition |
| S5 Medium | No owner backup procedure; data/key loss and prolonged outage possible | Operational failure possible; availability/security obligations | Weekly-due tool and synthetic recovery tests supplied | Schedule, protect, copy off-host, approve expiry and perform production-copy restore drill |
| S9 Medium unverified | Public mapping, host permissions, debug, logs, live cookie/security config unknown | Not established; could expose all data if wrong | Application has no database-serving route; backups refuse repo paths | Inspect PythonAnywhere Web/static mappings and WSGI; 404 probes alone do not prove all mappings safe |
| S8 Medium dependency | Advisory scan found cryptography 48.0.1 and pip 26.0.1 issues | Affected crypto APIs not directly used; pip requires malicious install input/index | Crypto minimum raised to patched major; isolated pip updated | Upgrade/test production dependencies; no claim that local audit describes live deployment |
| S6 Medium defence | Broad CSRF/auth attempt controls absent | Browser request protection and abuse/resource risk | CSRF, cross-origin rejection, shared hashed throttles and size caps implemented | Verify real REMOTE_ADDR and user flows on host; distributed abuse still needs monitoring |
| S10 Medium privacy | Children likely, but no child-focused DPIA or verified lawful child analytics processing | Plausible use, not proof of unlawful processing; Children's Code/COPPA applicability needs assessment | Analytics default off, no new age collection | Assess children and default settings before promoting service; specialist advice if required |
| S11 Medium operational | No confirmed incident-response process or restore exercises | Incident impact could be magnified; reportability/deadlines depend on risk | Incident runbook supplied | Store private contacts/log location, rehearse and record decisions; no incident alleged |
| S4 Low | Indefinite guest/delivery data and uncertain subscription/account lifecycle | Confirmed control gap; storage-limitation assessment | Preview-first cleanup, device removal implemented | Approve periods and production cleanup; no records removed automatically |
| S7 Low | Missing consistent headers/cache controls | Defence-in-depth, not demonstrated XSS | Limited CSP, framing/MIME/referrer/permissions/HSTS/no-store implemented | Full CSP and host TLS verification still needed |
| S12 Medium before expansion | Future ads/payment/marketing/international targeting can materially change obligations/costs | Future conditional risk | No new features or spending introduced | Reassess provider contracts, children's protection, direct marketing, competition rules and scope before enabling |

Risk acceptance is not a finding of legal compliance. Deployment remains gated
on the owner checklist, particularly secrets, backups and static mappings.
