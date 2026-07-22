# Threat Model

## Assets

Operator authorization records, target allowlists, scan or analysis results, audit
events, service credentials, and integration tokens are sensitive assets.

## Trust boundaries

Future boundaries include HTTP clients, workers, PostgreSQL, Redis, external tools, and
third-party integrations. All data crossing a boundary is untrusted.

## Initial controls

- No network-capable functionality in the foundation milestone
- Secrets excluded through `.gitignore`; placeholders only in `.env.example`
- Read-only GitHub Actions permissions
- Static analysis includes common Python security rules

Before target-facing features ship, a central validator must accept only localhost,
RFC1918/Docker networks, or explicit allowlist entries; reject public and unauthorized
targets; prevent DNS rebinding and ambiguous address forms; and emit redacted audit logs.

