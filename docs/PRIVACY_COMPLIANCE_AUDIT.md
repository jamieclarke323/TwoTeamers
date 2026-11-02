# Privacy and applicability assessment

2 November 2026. Technical assessment, not legal advice. Accessibility worldwide
does not itself establish that every jurisdiction's law applies. Owner facts:
predominantly UK football audience, possible children, no prizes, ads, paid entry
or marketing emails today; these may change. Reassess before those changes.

## Applicable regimes and decisions

| Regime / official source | Applicability and gap | Technical and owner actions / residual risk |
|---|---|---|
| [UK GDPR/DPA guidance](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/) | UK-established operator processes account/visitor personal data: applicable | Account functionality: proposed contract basis where necessary; essential security: assess legitimate interests; optional analytics/push: consent. Record purposes, recipients, rights and actual retention. A policy alone is not compliance |
| [PECR storage/access rules, including DUAA changes](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/) | Cookies/local storage and analytics are in scope. Statistical exception is conditional, not a blanket GA exemption | Conservative basic opt-in: do not contact Google before acceptance, provide reject/withdraw. Do not claim that advanced consent mode's cookieless pings are equivalent to no collection |
| [ICO exceptions](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guidance-on-the-use-of-storage-and-access-technologies/what-are-the-exceptions/) | Actual GA processing/account settings have not established the exception's conditions or simple objection requirement | No exception relied upon here. Essential account/security storage must be necessary; offline storage is user requested. Assess automatic How to play preference storage separately; do not assume all local storage is essential |
| [EU GDPR Articles 3, 8, 27, 33, 34, 44](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | Uncertain: targeting EU users or monitoring their behaviour can trigger scope, not mere access. Analytics makes monitoring relevant even without EU advertising | Assess actual EU users/processing, whether behavioural monitoring applies, national ePrivacy rules and any representative requirement. Opt-in is helpful, not proof of EU-wide compliance |
| [California CCPA](https://oag.ca.gov/privacy/ccpa) and [CPPA regulations](https://cppa.ca.gov/regulations/) | Not established; depends on for-profit business status and current adjusted revenue, 100,000 consumer/household buy/sell/share threshold, or 50% sell/share revenue tests. Mere Californian visits are insufficient | Owner has not supplied revenue/volume figures; do not declare an exemption. Check current thresholds and advertising data-sharing before monetisation |
| [Virginia official law](https://law.lis.virginia.gov/vacodepopularnames/consumer-data-protection-act/) and [Colorado AG](https://coag.gov/resources/colorado-privacy-act/) | Representative other state laws have distinct scope, volume, sale/revenue and exemptions. No evidence currently establishes applicability; this is not a complete 50-state assessment | Reassess real US scale and sale/sharing, and check relevant states individually. Smaller thresholds or special child/sensitive-data rules may change the result |
| [FTC COPPA rule](https://www.ftc.gov/legal-library/browse/rules/childrens-online-privacy-protection-rule-coppa) | Uncertain: child-directed service or actual knowledge of collecting US under-13 personal information can trigger requirements without large-business thresholds | Assess audience/content and known users. Possible child use alone is not a definitive COPPA finding. Do not collect dates of birth or implement intrusive age verification without necessity/proportionality review |
| [ICO Children's Code](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/) | Likely relevant: general-audience online services likely to be accessed by children need assessment; owner expects children may play | Document child-focused DPIA, high-privacy defaults, understandable notices, minimisation and no profiling-by-default. Do not treat a child's banner click as proof of lawful parental consent where required |
| [ICO fee checker](https://ico.org.uk/fee-checker) | Fee/exemption status not established | Owner must complete checker; sole ownership/hobby status is not automatically an exemption |
| [ICO breach guidance](https://ico.org.uk/for-organisations/report-a-breach/personal-data-breach/personal-data-breaches-a-guide/) | Applies to personal-data breaches; notification depends on risk | Notify ICO without undue delay and, where feasible, within 72 hours of awareness unless unlikely to risk rights/freedoms; high-risk cases require notifying individuals without undue delay. Record all decisions |

Other countries' rules remain fact-dependent and unassessed individually. No
geographic blocking was introduced. Obtain advice if deliberately expanding
abroad or collecting information about known children.

## Data inventory

| Data | Purpose/location/access | Sharing and proposed basis | Retention and deletion |
|---|---|---|---|
| Email, password hash, team | SQLite users; app/operator and authorised host access; login/personalisation | PythonAnywhere hosting; contract where necessary, security legitimate-interest assessment | Accounts currently remain until owner handles deletion; define inactivity/review period, not an invented automated deadline |
| Account scores/history | SQLite progress, account-isolated | Host; contract for saved history. Leaderboards show team aggregates, not account emails | Kept for account functionality; owner deletion must cascade related rows |
| Guest ID/results | Signed browser session plus guest_progress | Host; gameplay necessity and documented lawful-basis assessment | Cookie up to 30 days, results currently longer. Proposed cleanup: records not updated for 90 days; preview only until authorised |
| Session/CSRF tokens | Signed HttpOnly/SameSite cookies, rendered security tokens | No intentional third-party sharing; necessary security | Session up to 30 days; authentication clears prior session; no server revocation of every copied signed cookie yet |
| Hashed auth-limit buckets/times | SQLite auth_attempts; no stored raw address/email | Host; security legitimate interests | One hour; opportunistic cleanup and maintenance CLI |
| Offline packages and queued actions | Browser IndexedDB/cache; signed claims/state on server | No intentional analytics of answers; user-requested feature | Local play normally eight hours, sync acceptance seven days; local cleanup is lazy. Server cleanup seven days in CLI |
| Push endpoint/encryption keys/preferences | SQLite subscriptions/users; server/browser push service | Browser vendor push infrastructure; optional gameplay consent | Unsubscribe/device removal/account deletion/invalid endpoint cleanup. No proven complete stale-device expiry; decide and document policy |
| Delivery category/event/endpoint hash/status | SQLite delivery ledger | Host; minimisation/troubleshooting assessment | Proposed 90 days, preview-first. Avoid deleting recent idempotency records |
| GA browser/device/page usage and identifiers | Browser and Google's service only after opt-in | Google; consent. Google receives transport metadata including the connecting IP; do not claim no personal data | Local choice expires after 180 days; standard tag cookie lifetime capped at 180 days. GA event retention and reset-on-activity settings require Admin verification |
| How to play last visit | Browser local storage only | No intentional third-party sharing | Updated each visit; no automatic removal currently. Document necessity/exception or offer control if required |
| Hosting/security logs | PythonAnywhere; operator/host | Operational security; actual host terms to review | Host configuration and retention unknown; minimise raw logs and access |
| Backups | Private directory outside repo/public mappings; operator | No off-host provider selected | Weekly proposed schedule; no silent rotation. Approve an eight-week rolling policy and reconcile erasures with backup expiry before activation |

## GA4 and international transfers

The tag uses `G-XZLDYJXQ8V`, disables Google Signals and advertising personalisation
signals, and avoids sending query strings as the configured page location.
No account email, password, user ID or answer is explicitly sent by app code.
Enhanced measurement and future external tags can change collection; inspect
network requests and GA Admin, rather than assuming this proves no identifiable
information ever reaches Google.

Manual checks: [Google retention](https://support.google.com/analytics/answer/7667196),
[Google Signals](https://support.google.com/analytics/answer/9445345) and
[consent implementation](https://developers.google.com/tag-platform/security/guides/consent).
Prefer minimal event retention, no reset extension, no ads links/Signals/user-ID,
and disable unnecessary enhanced measurement (especially form/site-search capture).
Record actual settings in the owner's processing record.

Review Google and PythonAnywhere controller/processor terms, security/subprocessor
information and applicable UK/EEA transfer mechanism and assessment. Neither
hosting location nor a valid transfer arrangement was verified. Do not assert
data remains in the UK. Withdrawal stops future browser collection; historic
Google data/right requests need separate handling.

## Rights and communications

Use the published support address. Confirm identity proportionately; do not
request a password or identity document by default. Scope an authenticated
account request, export only that account's data, verify recipient, use a secure
delivery channel and record outcome. Do not create a public arbitrary export/
delete endpoint. Typical UK GDPR requests require action within one month,
subject to applicable extensions/exceptions; seek advice where uncertain.

Account deletion should transactionally delete the verified user with foreign
keys enabled, plus owner-bound offline sessions; guest-linked data may need
separate identification. Document backup suppression/expiry so restoration
does not silently reintroduce deleted users. Do not delete production records
until the request and scope are verified.

No marketing permission is inferred from signup or gameplay push consent.
Ads, marketing emails, paid entry and prizes require a fresh privacy, consumer,
children's and potentially competition/gambling assessment before launch.
