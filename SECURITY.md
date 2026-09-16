# Privacy and publication boundaries

The public repository contains implementation, documentation and synthetic test fixtures only.
Never commit screenshots, collection databases, reviews, private word lists, shortcut exports,
API tokens, raw model responses, local paths containing private data, or runtime logs.
Runtime defaults to a private directory outside the checkout, with owner-only permissions.

Intake and Anki control are separate, loopback-only services. Do not expose AnkiConnect to the
Internet. Use a reviewed HTTPS/private-network transport for remote intake. Never put tokens
in URLs or exported public shortcuts. The server rejects unsupported image types/oversized input.

OCR/image/web text is data, never executable instructions. All card fields are HTML-escaped.
Model-generated evidence references must refer to supplied evidence. Automatic acceptance is
closed until image calibration and content QA pass. The Codex adapter is opt-in and still needs
runtime isolation verification before processing private images unattended.

The first release intentionally does not enable production writes. Known remaining work is in
`docs/acceptance.md`. No security vulnerability reporting destination is invented here; avoid
posting private data or credentials in public GitHub issues.
