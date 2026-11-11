# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please do not open a public issue.

Instead, report it privately by contacting the repository owner.

Please include:
- A clear description of the issue
- Steps to reproduce
- Potential impact
- Suggested fix, if available

## Scope

Chess Trainer is a local, single-user app. By default it listens on `127.0.0.1` only and answers
only to `localhost` and `127.0.0.1`. Exposing it on a network, with `CHESS_TRAINER_ALLOWED_HOSTS`
or a different bind address, is at your own risk: it has no accounts and no login.

## Supported Versions

At this time, only the latest version of the project is supported with security updates.
