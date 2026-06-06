---
sidebar_position: 10
description: "FiestaBoard can encrypt secrets like API keys and board keys before writing them to disk. This is independent of the login feature."
keywords: [FiestaBoard secrets, encryption, Fernet, API keys, encryption key]
---

# Secret encryption at rest

FiestaBoard exposes a small helper module — `src.security.secrets` — that
encrypts string values with [Fernet](https://cryptography.io/en/latest/fernet/)
(AES-128-CBC + HMAC-SHA256) before they are written to disk.

This is a **draft / opt-in** primitive. New code that handles secrets can
call `encrypt_secret(value)` before persisting and `decrypt_secret(value)`
on read. Existing plaintext values are passed through unchanged, so the
two functions are safe to layer in incrementally.

## Why?

The unified container stores its full configuration in
`data/config.json`. If that file is leaked (backup snapshot, shared
volume, accidental `git add`…) any plaintext API keys travel with it.
Wrapping those values in an encrypted token shrinks the blast radius:
the attacker also needs the encryption key.

## How the key is loaded

In order of precedence:

1. `FIESTABOARD_SECRET_KEY` environment variable. Must be a urlsafe
   base64-encoded 32-byte Fernet key.
2. `data/.secret_key`. Auto-generated on first use, mode `0600`.

Generate a key manually:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

:::warning Back up the key
Encrypted secrets are unrecoverable without the key. If you let
FiestaBoard auto-generate one, back up `data/.secret_key` along with the
rest of `data/`.
:::

## API

```python
from src.security import encrypt_secret, decrypt_secret, is_encrypted

token = encrypt_secret("sk-...")       # -> "enc::v1::gAAAA..."
secret = decrypt_secret(token)         # -> "sk-..."

# Idempotent — already-encrypted values are returned unchanged.
encrypt_secret(token) == token

# Plaintext-aware — non-encrypted values pass through.
decrypt_secret("plain") == "plain"

# Detect ciphertext.
is_encrypted(token)  # True
```

Every encrypted value carries an `enc::v1::` prefix so callers can tell
plaintext from ciphertext during a migration without guessing.

## Rotating the key

`rotate_key(new_key, values=[...])` re-encrypts a list of values under a
new Fernet key and switches the process to it. The caller is responsible
for persisting `new_key` (env var or `data/.secret_key`) and writing the
new tokens back into config.

## Relationship to the login feature

The encryption key and the session-signing key are kept separate. A leak
of one does not compromise the other.
