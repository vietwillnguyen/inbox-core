"""Authenticated encryption for stored text, with key versioning."""

from __future__ import annotations

import base64
import secrets

import pytest

from inbox_core.crypto import (
    DecryptionError,
    EncryptionKeyError,
    FieldCipher,
    generate_key_entry,
    main,
    parse_keys,
)

PLAINTEXT = "I need to talk to someone about my child"


def key() -> bytes:
    return secrets.token_bytes(32)


def entry(key_id: str, raw: bytes) -> str:
    return f"{key_id}:{base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')}"


class TestRoundTrip:
    def test_encrypts_and_decrypts(self) -> None:
        cipher = FieldCipher({"k1": key()}, "k1")
        token = cipher.encrypt(PLAINTEXT, "messages.body")
        assert token.startswith("icenc:v1:k1:")
        assert PLAINTEXT not in token
        assert cipher.decrypt(token, "messages.body") == PLAINTEXT

    def test_each_encryption_uses_a_fresh_nonce(self) -> None:
        cipher = FieldCipher({"k1": key()}, "k1")
        assert cipher.encrypt("same", "c") != cipher.encrypt("same", "c")

    def test_optional_helpers_pass_none_through(self) -> None:
        cipher = FieldCipher({"k1": key()}, "k1")
        assert cipher.encrypt_optional(None, "c") is None
        assert cipher.decrypt_optional(None, "c") is None
        token = cipher.encrypt_optional("x", "c")
        assert token is not None
        assert cipher.decrypt_optional(token, "c") == "x"

    def test_a_custom_scheme_prefix(self) -> None:
        cipher = FieldCipher({"k1": key()}, "k1", scheme="vhenc")
        token = cipher.encrypt("x", "c")
        assert token.startswith("vhenc:v1:k1:")
        assert cipher.decrypt(token, "c") == "x"
        with pytest.raises(ValueError, match="scheme"):
            FieldCipher({"k1": key()}, "k1", scheme="Bad Scheme")


class TestAuthentication:
    def test_the_context_is_bound(self) -> None:
        cipher = FieldCipher({"k1": key()}, "k1")
        token = cipher.encrypt(PLAINTEXT, "messages.body")
        with pytest.raises(DecryptionError, match="failed authentication"):
            cipher.decrypt(token, "messages.subject")

    def test_a_flipped_byte_is_detected(self) -> None:
        cipher = FieldCipher({"k1": key()}, "k1")
        token = cipher.encrypt(PLAINTEXT, "c")
        prefix, payload = token.rsplit(":", 1)
        raw = bytearray(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        raw[-1] ^= 1
        tampered = f"{prefix}:{base64.urlsafe_b64encode(bytes(raw)).decode('ascii')}"
        with pytest.raises(DecryptionError):
            cipher.decrypt(tampered, "c")

    def test_a_wrong_key_under_the_same_id_is_detected(self) -> None:
        token = FieldCipher({"k1": key()}, "k1").encrypt(PLAINTEXT, "c")
        with pytest.raises(DecryptionError, match="failed authentication"):
            FieldCipher({"k1": key()}, "k1").decrypt(token, "c")

    def test_an_empty_string_round_trips(self) -> None:
        # A web chat message has no subject; its empty subject is still sealed
        # and must open again.
        cipher = FieldCipher({"k1": secrets.token_bytes(32)}, "k1")
        assert cipher.decrypt(cipher.encrypt("", "ctx"), "ctx") == ""

    def test_a_payload_shorter_than_nonce_and_tag_is_truncated(self) -> None:
        cipher = FieldCipher({"k1": secrets.token_bytes(32)}, "k1")
        short = base64.urlsafe_b64encode(b"x" * 27).decode()
        with pytest.raises(DecryptionError, match="truncated"):
            cipher.decrypt(f"icenc:v1:k1:{short}", "ctx")

    @pytest.mark.parametrize(
        ("token", "problem"),
        [
            ("plain text", "not an encrypted value"),
            ("icenc:v2:k1:AAAA", "unknown scheme version"),
            ("icenc:v1:k9:AAAA", "key id 'k9'"),
            ("icenc:v1:k1:!!!!", "not valid base64"),
            ("icenc:v1:k1:AAAA", "truncated"),
            ("other:v1:k1:AAAA", "not an encrypted value"),
        ],
    )
    def test_malformed_tokens(self, token: str, problem: str) -> None:
        cipher = FieldCipher({"k1": key()}, "k1")
        with pytest.raises(DecryptionError, match=problem):
            cipher.decrypt(token, "messages.body", ids="message id=4")

    def test_errors_name_ids_never_plaintext_or_keys(self) -> None:
        raw = key()
        cipher = FieldCipher({"k1": raw}, "k1")
        token = cipher.encrypt(PLAINTEXT, "messages.body")
        with pytest.raises(DecryptionError) as caught:
            cipher.decrypt(token, "messages.subject", ids="message id=4")
        shown = str(caught.value)
        assert "message id=4" in shown
        assert PLAINTEXT not in shown
        assert token not in shown
        assert base64.urlsafe_b64encode(raw).decode()[:10] not in shown


class TestKeyVersioning:
    def test_rotation_keeps_old_values_readable(self) -> None:
        old, new = key(), key()
        before = parse_keys(entry("k1", old))
        token = before.encrypt(PLAINTEXT, "c")
        after = parse_keys(f"{entry('k2', new)},{entry('k1', old)}")
        assert after.primary_key_id == "k2"
        assert after.key_ids == ("k1", "k2")
        assert after.decrypt(token, "c") == PLAINTEXT
        assert after.encrypt("x", "c").startswith("icenc:v1:k2:")

    def test_reencrypt_moves_a_value_onto_the_primary_key(self) -> None:
        old, new = key(), key()
        token = parse_keys(entry("k1", old)).encrypt(PLAINTEXT, "c")
        rotated = parse_keys(f"{entry('k2', new)},{entry('k1', old)}")
        moved = rotated.reencrypt(token, "c")
        assert moved.startswith("icenc:v1:k2:")
        assert parse_keys(entry("k2", new)).decrypt(moved, "c") == PLAINTEXT

    def test_the_primary_key_must_exist(self) -> None:
        with pytest.raises(EncryptionKeyError, match="primary"):
            FieldCipher({"k1": key()}, "k2")

    def test_keys_must_be_32_bytes(self) -> None:
        with pytest.raises(EncryptionKeyError, match="32 bytes"):
            FieldCipher({"k1": b"short"}, "k1")


class TestParseKeys:
    @pytest.mark.parametrize(
        ("raw", "problem"),
        [
            (None, "not set"),
            ("  ", "not set"),
            (f"k1:{base64.urlsafe_b64encode(bytes(32)).decode()},,", "entry 2 is empty"),
            ("no-separator", "must look like"),
            ("K1:AAAA", "must look like"),
            ("k1:not*base64", "not valid base64url"),
            ("k1:" + base64.urlsafe_b64encode(b"x" * 16).decode(), "32 bytes"),
        ],
    )
    def test_malformed_settings(self, raw: str | None, problem: str) -> None:
        with pytest.raises(EncryptionKeyError, match=problem):
            parse_keys(raw)

    def test_a_duplicate_key_id(self) -> None:
        raw = key()
        with pytest.raises(EncryptionKeyError, match="more than once"):
            parse_keys(f"{entry('k1', raw)},{entry('k1', raw)}")

    def test_errors_name_the_setting_and_never_the_value(self) -> None:
        secret_material = base64.urlsafe_b64encode(b"y" * 16).decode()
        with pytest.raises(EncryptionKeyError) as caught:
            parse_keys(f"k1:{secret_material}", setting="CLIENT_KEYS")
        assert "CLIENT_KEYS" in str(caught.value)
        assert secret_material not in str(caught.value)

    def test_repr_never_shows_key_material(self) -> None:
        raw = key()
        cipher = parse_keys(entry("k1", raw))
        shown = repr(cipher) + str(cipher)
        assert "k1" in shown
        assert base64.urlsafe_b64encode(raw).decode()[:10] not in shown


class TestGenerate:
    def test_a_generated_entry_parses(self) -> None:
        generated = generate_key_entry("k3")
        assert generated.startswith("k3:")
        assert parse_keys(generated).primary_key_id == "k3"

    def test_a_bad_key_id_is_refused(self) -> None:
        with pytest.raises(EncryptionKeyError, match="key id"):
            generate_key_entry("Not OK")

    def test_the_command_line_prints_an_entry(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["generate-key", "--key-id", "k7"]) == 0
        printed = capsys.readouterr().out.strip()
        assert parse_keys(printed).primary_key_id == "k7"
