# Security notes — US Earnings Intelligence Terminal

Last audited: Oct 29, 2026.

## API keys (tokens)

- Both provider keys live ONLY as GitHub Actions repository secrets
  (`TWELVE_DATA`, `FMP_KEY`). GitHub encrypts secrets at rest and masks
  their values in workflow logs. Secret values are never readable back —
  not by collaborators, not by the automation that pushes this repo.
- No key, token, or password exists in any file in this repository
  (verified by pattern scan, Oct 29 2026). The fetch scripts read the keys
  from environment variables injected by the workflow at runtime.
- Both fetch scripts additionally scrub the key value out of every error
  message before printing (`scrub()`), so a transport error that echoes a
  request URL cannot leak a key into a log.
- If a key is ever suspected compromised: revoke it at the provider,
  generate a new one, and replace the repository secret value. No code
  change is needed.

## What is public

- This repository is currently PUBLIC, and GitHub Pages serves the
  terminal publicly. Everything committed here — code, data files, and
  any transcripts the workflow fetches — is world-readable.
- SEC EDGAR requires a declared contact in the User-Agent; the data-layer
  script carries a business contact email for that purpose.
- Market data committed by the workflow (prices, reactions, calendar) is
  public market information. Provider-licensed content (e.g. earnings
  call transcripts) carries redistribution terms — review the provider
  licence before relying on public hosting of fetched transcripts.

## The privacy decision (owner's call)

Making this repository private would take the public Pages site offline
on a free GitHub plan (private-repo Pages needs a paid plan). Options:

1. Stay public (current) — treat everything committed as published.
2. Go private + paid plan — Pages keeps working, content restricted.
3. Go private + serve the terminal elsewhere — most work, most control.

Until the owner chooses, the operating rule is option 1: never commit
anything to this repository that should not be public.
