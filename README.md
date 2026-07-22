# RedMind

Controlled adversarial planning research for cyber ranges.

> Status: foundation only. Runtime services and domain features are intentionally deferred.

## Features

- Typed Python 3.12 package foundation
- Reproducible lint, type-check, and test commands
- CI quality gate and public-project governance
- Documented safety boundary for authorized research

## Installation

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Running

There is no runtime service in this foundation release. Run all quality checks with:

```bash
make check
```

Service commands will be added when the API or worker boundary is implemented.

## Architecture

The initial package uses a `src/` layout and keeps tests outside production code.
Future API, worker, persistence, and integration boundaries must remain independently
testable. See [docs/architecture.md](docs/architecture.md).

## Limitations

- No API, database, worker, or web interface exists yet.
- No scanner, exploit, response action, or external integration is implemented.
- The target allowlist enforcement layer is planned and must precede target-facing features.

## Security policy

Use is limited to systems owned by the operator, local/Docker labs, CTFs, educational
cyber ranges, and explicitly authorized targets. Public internet discovery, credential
theft, persistence, defensive-control bypass, malware delivery, and destructive or
exfiltration behavior are out of scope. See [SECURITY.md](SECURITY.md) and
[docs/threat-model.md](docs/threat-model.md).

## Roadmap

The next milestone defines the domain model and target-validation boundary before any
network-capable behavior. See [docs/roadmap.md](docs/roadmap.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). This project is licensed under the MIT License.

