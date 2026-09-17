# Security Policy

## Supported version

| Version | Support |
| --- | --- |
| 0.0.2 | Security and critical reliability fixes |
| 0.0.1-r7 | Security and critical reliability fixes |
| 0.0.1-r6 | Security and critical reliability fixes |
| 0.0.1-r5-r1 | Security and critical reliability fixes |
| 0.0.1-r5 | Security and critical reliability fixes |
| 0.0.1-r4 | Security and critical reliability fixes |

## Reporting a vulnerability

Do not disclose a suspected vulnerability in a public issue. Contact the
maintainer privately through the GitHub profile associated with the project.
Include the affected version, runtime mode, distribution, reproduction steps,
potential impact, and relevant logs or proof of concept.

Rico Plus edits user-controlled files but does not execute them. Important
security boundaries include Workspace path containment, symbolic-link target
validation, replacement races, atomic saves, external application launching,
configuration permissions, and avoiding silent data loss.
