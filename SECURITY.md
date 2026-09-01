# Security Policy

## Supported versions

Security fixes are provided for the latest released version of tokens.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue for a vulnerability that could expose local paths, session identifiers, log contents, generated reports, or other sensitive data.

Include:

- the affected version and platform;
- a minimal reproduction using synthetic data;
- the expected and observed behavior;
- the potential privacy or security impact.

Do not attach real AI CLI logs or generated dashboards. Remove usernames, project paths, session IDs, prompts, credentials, and tokens from diagnostic output.

## Security model

tokens reads local files and generates local reports. It does not upload analytics or load remote runtime assets. Generated dashboards can still contain sensitive local metadata. `--anonymize` replaces selected identifiers with report-scoped pseudonyms; it is not a guarantee that a report is safe to publish.
