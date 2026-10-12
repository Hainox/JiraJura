# Security: the non-obvious part

You already know OWASP. These are the checks that get skipped:

- Authorize per **object**, not per route: confirm the caller owns *this* record, every read and write.
- Log identifiers, never credentials, tokens, or personal data; error responses carry a message, never a stack trace.
- A secret found in code or git history is already leaked: stop, tell the human which secret and where. Rotation is theirs; deleting the line does not un-leak it.
- New endpoints inherit the project's existing rate limiting and auth middleware; if none applies, say so rather than ship it open.
