"""Authenticated encryption for stored conversation text, with key versioning.

Every subject, body, sender address and reply a store keeps goes through a
:class:`FieldCipher`, so a copy of the database on its own - a leaked backup,
a mis-shared export - cannot be read.

The scheme is AES-256-GCM from ``cryptography``: authenticated, so a wrong
key, a flipped byte or a token moved into another column fails loudly rather
than decrypting to garbage. The ``context`` (the column a value belongs to) is
bound in as associated data for the same reason.

Stored form, one ASCII string per value::

    <scheme>:v1:<key id>:<base64url(12-byte nonce || ciphertext || 16-byte tag)>

The key setting is a comma-separated list of ``<key id>:<base64url of 32
bytes>`` entries. The first entry encrypts everything new and every entry can
decrypt, so rotating is: generate a key (``python -m inbox_core.crypto
generate-key --key-id k2``), put it in front of the old one, deploy. Old values
keep reading with the old key; :meth:`FieldCipher.reencrypt` moves one onto the
new key if that is ever wanted.

Nothing here logs. Errors name the setting, the key id and whatever ids the
caller supplies, never key material, tokens or plaintext.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import re
import secrets
import sys
from collections.abc import Mapping, Sequence

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

__all__ = [
    "DEFAULT_SETTING",
    "DecryptionError",
    "EncryptionKeyError",
    "FieldCipher",
    "generate_key_entry",
    "main",
    "parse_keys",
]

DEFAULT_SETTING = "INBOX_ENCRYPTION_KEYS"
"""The environment variable name used in messages when the caller names none."""

VERSION = "v1"
KEY_BYTES = 32
NONCE_BYTES = 12

_KEY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
_SCHEME = re.compile(r"^[a-z][a-z0-9]{1,15}$")


class EncryptionKeyError(ValueError):
    """The key setting is missing or malformed. Names the setting, never the value."""


class DecryptionError(Exception):
    """A stored value could not be decrypted. Names ids, never the value."""


def _b64decode(encoded: str) -> bytes:
    """Strict base64url: anything outside the alphabet is an error, not skipped."""
    padded = encoded + "=" * (-len(encoded) % 4)
    return base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)


class FieldCipher:
    """Encrypts and decrypts single values. Holds the keys; never shows them."""

    def __init__(
        self, keys: Mapping[str, bytes], primary_key_id: str, *, scheme: str = "icenc"
    ) -> None:
        if primary_key_id not in keys:
            raise EncryptionKeyError("the key set has no entry for its primary key id")
        if not _SCHEME.match(scheme):
            raise ValueError("scheme must be 2 to 16 lower-case letters or digits")
        for key_id, key in keys.items():
            if len(key) != KEY_BYTES:
                raise EncryptionKeyError(f"key id {key_id!r} must be {KEY_BYTES} bytes")
        self._keys = {key_id: AESGCM(key) for key_id, key in keys.items()}
        self.primary_key_id = primary_key_id
        self.scheme = scheme

    def __repr__(self) -> str:
        return f"FieldCipher(primary_key_id={self.primary_key_id!r}, key_ids={self.key_ids!r})"

    __str__ = __repr__

    @property
    def key_ids(self) -> tuple[str, ...]:
        """Every key id this cipher can decrypt with, sorted."""
        return tuple(sorted(self._keys))

    def encrypt(self, plaintext: str, context: str) -> str:
        """``plaintext`` sealed under the primary key, bound to ``context``."""
        nonce = secrets.token_bytes(NONCE_BYTES)
        sealed = self._keys[self.primary_key_id].encrypt(
            nonce, plaintext.encode("utf-8"), context.encode("utf-8")
        )
        payload = base64.urlsafe_b64encode(nonce + sealed).decode("ascii")
        return f"{self.scheme}:{VERSION}:{self.primary_key_id}:{payload}"

    def decrypt(self, token: str, context: str, *, ids: str = "") -> str:
        """The plaintext of ``token``, or :class:`DecryptionError` naming ``ids``."""
        where = f"{context}{f' ({ids})' if ids else ''}"
        parts = (token or "").split(":", 3)
        if len(parts) != 4 or parts[0] != self.scheme:
            raise DecryptionError(f"{where} is not an encrypted value")
        _scheme, version, key_id, payload = parts
        if version != VERSION:
            raise DecryptionError(f"{where} uses unknown scheme version {version!r}")
        aead = self._keys.get(key_id)
        if aead is None:
            raise DecryptionError(f"{where} was encrypted with key id {key_id!r}, which is not set")
        try:
            raw = _b64decode(payload)
        except (binascii.Error, ValueError, UnicodeEncodeError):
            raise DecryptionError(f"{where} is not valid base64") from None
        if len(raw) <= NONCE_BYTES + 16:
            raise DecryptionError(f"{where} is truncated")
        try:
            opened = aead.decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], context.encode("utf-8"))
        except InvalidTag:
            raise DecryptionError(
                f"{where} failed authentication with key id {key_id!r}: wrong key, "
                "tampered value, or a value moved from another column"
            ) from None
        return opened.decode("utf-8")

    def encrypt_optional(self, plaintext: str | None, context: str) -> str | None:
        """:meth:`encrypt`, passing None through."""
        return None if plaintext is None else self.encrypt(plaintext, context)

    def decrypt_optional(self, token: str | None, context: str, *, ids: str = "") -> str | None:
        """:meth:`decrypt`, passing None through."""
        return None if token is None else self.decrypt(token, context, ids=ids)

    def reencrypt(self, token: str, context: str, *, ids: str = "") -> str:
        """``token`` re-sealed under the primary key, for a rotation clean-up."""
        return self.encrypt(self.decrypt(token, context, ids=ids), context)


def parse_keys(
    raw: str | None, *, setting: str = DEFAULT_SETTING, scheme: str = "icenc"
) -> FieldCipher:
    """A cipher from a key setting's value, or :class:`EncryptionKeyError` naming ``setting``."""
    if raw is None or not raw.strip():
        raise EncryptionKeyError(
            f"{setting} is not set. Generate one with "
            "`python -m inbox_core.crypto generate-key` and set it in the service environment."
        )
    keys: dict[str, bytes] = {}
    order: list[str] = []
    for position, item in enumerate(raw.split(","), start=1):
        part = item.strip()
        if not part:
            raise EncryptionKeyError(f"{setting} entry {position} is empty")
        key_id, separator, encoded = part.partition(":")
        key_id = key_id.strip()
        if not separator or not _KEY_ID.match(key_id):
            raise EncryptionKeyError(
                f"{setting} entry {position} must look like <key id>:<base64url key>, "
                "with a lower-case key id of at most 16 characters"
            )
        try:
            key = _b64decode(encoded.strip())
        except (binascii.Error, ValueError, UnicodeEncodeError):
            raise EncryptionKeyError(
                f"{setting} entry {position} (key id {key_id!r}) is not valid base64url"
            ) from None
        if len(key) != KEY_BYTES:
            raise EncryptionKeyError(
                f"{setting} entry {position} (key id {key_id!r}) must decode to {KEY_BYTES} bytes"
            )
        if key_id in keys:
            raise EncryptionKeyError(f"{setting} names key id {key_id!r} more than once")
        keys[key_id] = key
        order.append(key_id)
    return FieldCipher(keys, order[0], scheme=scheme)


def generate_key_entry(key_id: str) -> str:
    """A fresh ``<key id>:<key>`` entry for the key setting."""
    if not _KEY_ID.match(key_id):
        raise EncryptionKeyError(
            "a key id must be lower-case letters, digits, '-' or '_', at most 16"
        )
    key = base64.urlsafe_b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")
    return f"{key_id}:{key}"


def main(argv: Sequence[str] | None = None) -> int:
    """``python -m inbox_core.crypto generate-key [--key-id k1]``."""
    parser = argparse.ArgumentParser(
        prog="python -m inbox_core.crypto", description="Manage conversation encryption keys."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate-key", help="print a new key setting entry")
    generate.add_argument("--key-id", default="k1")
    args = parser.parse_args(argv)
    print(generate_key_entry(args.key_id))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
