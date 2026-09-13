"""LZF compression, as used by Krita for paint-layer tile data.

Ported from liblzf (Marc Lehmann, BSD-2-Clause) without the unrolled
fast paths. Krita prefixes each compressed tile blob with a one-byte
flag: 1 = LZF stream follows, 0 = raw bytes follow.
"""

MAX_LIT = 1 << 5
MAX_OFF = 1 << 13
MAX_REF = (1 << 8) + (1 << 3)
HLOG = 16
HSIZE = 1 << HLOG


def decompress(data: bytes, expected: int) -> bytes:
    out = bytearray()
    ip, n = 0, len(data)
    while ip < n and len(out) < expected:
        ctrl = data[ip]
        ip += 1
        if ctrl < 32:                      # literal run of ctrl+1 bytes
            ln = ctrl + 1
            out += data[ip:ip + ln]
            ip += ln
        else:                              # back-reference
            ln = ctrl >> 5
            if ln == 7:
                ln += data[ip]
                ip += 1
            ref = len(out) - ((ctrl & 0x1F) << 8) - data[ip] - 1
            ip += 1
            if ref < 0:
                raise ValueError("corrupt LZF stream: negative back-reference")
            for _ in range(ln + 2):
                out.append(out[ref])
                ref += 1
    return bytes(out)


def compress(inp: bytes) -> bytes:
    n = len(inp)
    if n == 0:
        return b""

    htab = [0] * HSIZE
    out = bytearray()
    ip = 0
    lit = 0
    out.append(0)                          # placeholder for first literal run

    def frst(p):
        return (inp[p] << 8) | inp[p + 1]

    def nxt(v, p):
        return ((v << 8) | inp[p + 2]) & 0xFFFFFF

    def idx(h):
        return ((h >> (3 * 8 - HLOG)) - h * 5) & (HSIZE - 1)

    if n > 2:
        hval = frst(ip)
        while ip < n - 2:
            hval = nxt(hval, ip)
            slot = idx(hval)
            ref = htab[slot]
            htab[slot] = ip
            off = ip - ref - 1

            if (ref < ip and off < MAX_OFF and ref > 0
                    and inp[ref] == inp[ip]
                    and inp[ref + 1] == inp[ip + 1]
                    and inp[ref + 2] == inp[ip + 2]):
                # The first three bytes are already known equal, so the
                # match is at least 3 long. This minimum is load-bearing:
                # a 2-byte match encodes to a control byte < 32, which the
                # decoder would read back as a literal run.
                maxlen = min(n - ip - 2, MAX_REF)
                ln = 3
                while ln < maxlen and inp[ref + ln] == inp[ip + ln]:
                    ln += 1

                if lit:
                    out[len(out) - lit - 1] = lit - 1   # close the literal run
                else:
                    out.pop()              # drop the unused run placeholder

                ln -= 2
                ip += 1
                if ln < 7:
                    out.append((off >> 8) + (ln << 5))
                else:
                    out.append((off >> 8) + (7 << 5))
                    out.append(ln - 7)
                out.append(off & 0xFF)

                lit = 0
                out.append(0)              # placeholder for next literal run
                ip += ln + 1
                if ip >= n - 2:
                    break
                hval = frst(ip)
            else:
                out.append(inp[ip])
                ip += 1
                lit += 1
                if lit == MAX_LIT:
                    out[len(out) - lit - 1] = lit - 1
                    lit = 0
                    out.append(0)

    while ip < n:
        out.append(inp[ip])
        ip += 1
        lit += 1
        if lit == MAX_LIT:
            out[len(out) - lit - 1] = lit - 1
            lit = 0
            out.append(0)

    if lit:
        out[len(out) - lit - 1] = lit - 1
    else:
        out.pop()
    return bytes(out)
