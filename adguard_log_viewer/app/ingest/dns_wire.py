"""Minimal DNS message decoder.

``querylog.json`` stores the response as a base64-encoded raw DNS message, so
reading the file directly means decoding the wire format. Only what the viewer
displays is decoded: the response code and the answer section. Anything
unparseable degrades to an empty answer list rather than raising — a truncated
line in a rotated log must never stop ingest.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import struct

from app.ingest.records import DnsAnswer

RCODE_NAMES: dict[int, str] = {
    0: "NOERROR",
    1: "FORMERR",
    2: "SERVFAIL",
    3: "NXDOMAIN",
    4: "NOTIMP",
    5: "REFUSED",
    6: "YXDOMAIN",
    7: "YXRRSET",
    8: "NXRRSET",
    9: "NOTAUTH",
    10: "NOTZONE",
    16: "BADVERS",
}

RR_TYPE_NAMES: dict[int, str] = {
    1: "A", 2: "NS", 5: "CNAME", 6: "SOA", 12: "PTR", 15: "MX", 16: "TXT",
    17: "RP", 24: "SIG", 25: "KEY", 28: "AAAA", 29: "LOC", 33: "SRV",
    35: "NAPTR", 36: "KX", 37: "CERT", 39: "DNAME", 41: "OPT", 43: "DS",
    46: "RRSIG", 47: "NSEC", 48: "DNSKEY", 50: "NSEC3", 51: "NSEC3PARAM",
    52: "TLSA", 59: "CDS", 60: "CDNSKEY", 61: "OPENPGPKEY", 64: "SVCB",
    65: "HTTPS", 99: "SPF", 108: "EUI48", 109: "EUI64", 249: "TKEY",
    250: "TSIG", 251: "IXFR", 252: "AXFR", 255: "ANY", 256: "URI",
    257: "CAA", 32768: "TA", 32769: "DLV",
}

_MAX_JUMPS = 32


class _Reader:
    __slots__ = ("data", "pos")

    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def read(self, size: int) -> bytes:
        end = self.pos + size
        if end > len(self.data):
            raise ValueError("truncated DNS message")
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack("!H", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("!I", self.read(4))[0]

    def name(self) -> str:
        """Read a (possibly compressed) domain name."""
        parts: list[str] = []
        pos = self.pos
        jumps = 0
        moved = False

        while True:
            if pos >= len(self.data):
                raise ValueError("truncated name")
            length = self.data[pos]

            if length == 0:
                pos += 1
                break
            if length & 0xC0 == 0xC0:
                if pos + 1 >= len(self.data):
                    raise ValueError("truncated pointer")
                pointer = ((length & 0x3F) << 8) | self.data[pos + 1]
                if not moved:
                    self.pos = pos + 2
                    moved = True
                jumps += 1
                if jumps > _MAX_JUMPS:
                    raise ValueError("compression loop")
                pos = pointer
                continue
            if length > 63:
                raise ValueError("bad label length")

            start = pos + 1
            end = start + length
            if end > len(self.data):
                raise ValueError("truncated label")
            parts.append(self.data[start:end].decode("ascii", "replace"))
            pos = end

        if not moved:
            self.pos = pos
        return ".".join(parts)


def _decode_rdata(reader: _Reader, rtype: int, rdlength: int) -> str:
    end = reader.pos + rdlength
    try:
        if rtype == 1 and rdlength == 4:
            return str(ipaddress.IPv4Address(reader.read(4)))
        if rtype == 28 and rdlength == 16:
            return str(ipaddress.IPv6Address(reader.read(16)))
        if rtype in (2, 5, 12, 39):
            return reader.name()
        if rtype == 15:
            preference = reader.u16()
            return f"{preference} {reader.name()}"
        if rtype == 16:
            chunks: list[str] = []
            while reader.pos < end:
                size = reader.u8()
                chunks.append(reader.read(size).decode("utf-8", "replace"))
            return "".join(chunks)
        if rtype == 33:
            priority, weight, port = reader.u16(), reader.u16(), reader.u16()
            return f"{priority} {weight} {port} {reader.name()}"
        if rtype == 6:
            primary = reader.name()
            mailbox = reader.name()
            serial = reader.u32()
            return f"{primary} {mailbox} {serial}"
        if rtype in (64, 65):
            priority = reader.u16()
            target = reader.name()
            return f"{priority} {target or '.'}"
        if rtype == 257:
            flags = reader.u8()
            tag_len = reader.u8()
            tag = reader.read(tag_len).decode("ascii", "replace")
            value = reader.read(max(0, end - reader.pos)).decode("utf-8", "replace")
            return f"{flags} {tag} {value}"
    except ValueError:
        pass
    finally:
        reader.pos = end

    return ""


def parse_message(data: bytes) -> tuple[str, list[DnsAnswer]]:
    """Return ``(rcode_name, answers)`` for a raw DNS message."""
    if len(data) < 12:
        return "", []

    reader = _Reader(data)
    try:
        reader.u16()  # transaction id
        flags = reader.u16()
        qdcount = reader.u16()
        ancount = reader.u16()
        reader.u16()  # nscount
        reader.u16()  # arcount

        rcode = RCODE_NAMES.get(flags & 0x0F, f"RCODE{flags & 0x0F}")

        for _ in range(qdcount):
            reader.name()
            reader.u16()  # qtype
            reader.u16()  # qclass

        answers: list[DnsAnswer] = []
        for _ in range(min(ancount, 64)):
            reader.name()
            rtype = reader.u16()
            reader.u16()  # class
            ttl = reader.u32()
            rdlength = reader.u16()
            value = _decode_rdata(reader, rtype, rdlength)
            answers.append(
                DnsAnswer(type=RR_TYPE_NAMES.get(rtype, str(rtype)), value=value, ttl=ttl)
            )
    except ValueError:
        return "", []

    return rcode, answers


def parse_base64_message(payload: str | None) -> tuple[str, list[DnsAnswer]]:
    """Decode the base64 ``Answer`` field of ``querylog.json``."""
    if not payload:
        return "", []
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        return "", []
    return parse_message(raw)
