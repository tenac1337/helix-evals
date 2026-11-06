# Credential handling

Copy `.env.template` to `.env` and enter your credentials locally. The template
must contain blank credential values only. Do not commit tokens, private keys,
credential files, or logs that contain authentication data.

Install the local commit hook before making changes:

```bash
pip install pre-commit
pre-commit install
```

The pinned Gitleaks hook scans staged changes. GitHub Actions also scans fetched
Git history on pushes and pull requests. To check locally with Gitleaks:

```bash
gitleaks git . --log-opts="--all --full-history" --redact=100
```

If a credential is committed, revoke or rotate it at its provider immediately.
Removing the file in a later commit does not remove earlier versions. Rewrite
every affected branch and tag, and contact GitHub Support about retained pull
request references and cached commits when necessary. Never include credential
values in issues, pull requests, or incident reports.

After a history cleanup, make a fresh clone. Do not merge or push old history
back into the repository. Preserve uncommitted work separately and inspect it
for credentials before applying it to the fresh clone.
