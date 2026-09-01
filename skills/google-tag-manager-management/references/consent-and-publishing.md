# Consent mode and publishing gates

## Consent mode principles

Consent configuration is a product/legal decision represented in code. This skill can implement and verify an approved model but must not decide which consent is legally required.

The current consent mode fields include:

- `ad_storage`
- `analytics_storage`
- `ad_user_data`
- `ad_personalization`

Set defaults before measurement. Update consent when the user's choice becomes available. Avoid delayed default commands that let tags race ahead of consent state.

For GTM custom templates, prefer the Tag Manager consent APIs documented by Google:

- `setDefaultConsentState`
- `updateConsentState`

They provide ordering semantics appropriate to the template sandbox. Do not substitute a queued `gtag` call where execution order is material.

Authoritative sources:

- Consent mode overview: <https://developers.google.com/tag-platform/security/guides/consent>
- GTM custom-template consent APIs: <https://developers.google.com/tag-platform/tag-manager/templates/consent-apis>

## Consent test matrix

Test at least:

| Case                                  | Expected evidence                                                |
| ------------------------------------- | ---------------------------------------------------------------- |
| Initial default before choice         | Correct default state is visible before measurement requests     |
| Explicit denial                       | Restricted tags do not fire; consent parameters reflect denial   |
| Explicit grant                        | Intended tags fire once with granted consent                     |
| Denied to granted update              | Subsequent behavior changes without duplicate initialization     |
| Granted to denied update              | Later measurement honors withdrawal where supported              |
| Region-specific default               | Only intended regions receive the regional default               |
| Page navigation or SPA transition     | Consent persists and tags do not duplicate                       |
| Preview versus production environment | Environment-specific behavior matches the reviewed configuration |

Inspect Tag Assistant's consent view and browser network traffic. A tag reporting "fired" does not prove the downstream request carried the intended consent state.

## Pre-version gate

- Workspace status is current.
- Sync returned no unresolved conflicts.
- All changed resources and references are reviewed.
- Fingerprints match the reviewed revision.
- Quick preview/compiler check succeeds.
- Tag Assistant passes firing and non-firing cases.
- Consent, privacy, duplicate-event, and payload checks pass.
- A prior live version is identified for rollback.

## Version creation warning

Creating a container version removes the source workspace and advances the version base. Capture:

- workspace ID and name;
- change set and fingerprints;
- returned container version ID;
- compiler status and any errors;
- previous live version ID.

Do not attempt version creation while conflicts remain.

## Publish gate

- The exact version ID and fingerprint are reviewed.
- The environment and account/container IDs are explicit.
- The user has authorized publication, not merely version creation.
- An acceptable publish scope reported by current Discovery metadata and the GTM permission are confirmed.
- The helper/API preview is retained without credentials.
- The publish response has no compiler error.
- The live version is re-read and matches the intended version.
- Runtime smoke tests pass in the deployed environment.

## Rollback

Rollback is another publication, not a local undo. Select a known-good prior version, review changes since that version, publish it with current concurrency data, and verify the live version plus runtime behavior. Record why the rollback was needed and preserve the failed version for analysis.
