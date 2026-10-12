# Security: the non-obvious part

You already know OWASP. These are the checks that get skipped:

- Authorize per **object**, not per route: on every read and write, check that the caller may act on *this* record under the project's access model (owner, member, role, district, service token), not just that they are signed in.
- Log identifiers, never credentials, tokens, or personal data; error responses carry a message, never a stack trace.
- A secret found in code or git history is already leaked: stop, tell the human which secret and where. Rotation is theirs; deleting the line does not un-leak it.
- A new endpoint gets the project's auth and rate limiting the same way its neighbours do: check whether that is middleware or a per-endpoint dependency, and wire it explicitly when it is the latter; if none applies, say so rather than ship it open.
