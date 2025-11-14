import base64
import hashlib
import hmac
import time


class DeepLinkCodec:
    """Кодек для deep-link payload на основе HMAC."""

    def __init__(self, secret: bytes | str, *, tag_len: int = 16, ttl: int | None = None) -> None:
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        if not (8 <= tag_len <= 32):
            msg = "tag_len должен быть в диапазоне [8, 32]"
            raise ValueError(msg)
        self._secret = secret
        self._tag_len = tag_len
        self._ttl = ttl

    def encode(self, payload_bytes: bytes) -> bytes:
        """Возвращает urlsafe base64 без '=' (bytes).

        Формат: base64url( ts(4) | payload | tag(tag_len) )
        """
        ts = self._u32(int(time.time()))
        tag = self._hmac(ts + payload_bytes)[: self._tag_len]
        token_raw = ts + payload_bytes + tag
        return self._b64url_nopad(token_raw)

    def decode(self, token: bytes) -> bytes:
        """Принимает token в виде urlsafe base64 без '=' (bytes).

        Возвращает исходный payload (bytes).
        """
        raw = self._b64url_nopad_decode(token)

        if len(raw) < 4 + self._tag_len:
            msg = "Токен слишком короткий или повреждён"
            raise ValueError(msg)

        ts = self._from_u32(raw[:4])
        payload = raw[4 : -self._tag_len]
        tag = raw[-self._tag_len :]

        expected = self._hmac(self._u32(ts) + payload)[: self._tag_len]
        if not hmac.compare_digest(tag, expected):
            msg = "Неверная подпись токена"
            raise ValueError(msg)

        if self._ttl is not None:
            now_i = int(time.time())
            if now_i > ts + self._ttl:
                msg = "Токен истёк (TTL)"
                raise ValueError(msg)

        return payload

    def _hmac(self, data: bytes) -> bytes:
        return hmac.new(self._secret, data, hashlib.sha256).digest()

    @staticmethod
    def _u32(x: int) -> bytes:
        return x.to_bytes(4, "big", signed=False)

    @staticmethod
    def _from_u32(b: bytes) -> int:
        return int.from_bytes(b, "big", signed=False)

    @staticmethod
    def _b64url_nopad(b: bytes) -> bytes:
        return base64.urlsafe_b64encode(b).rstrip(b"=")

    @staticmethod
    def _b64url_nopad_decode(s: bytes) -> bytes:
        pad = b"=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s + pad)
