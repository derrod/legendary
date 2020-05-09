# this is the rolling hash Epic uses, it appears to be a variation on CRC-64-ECMA

hash_poly = 0xC96C5795D7870F42
hash_table = []


def _init():
    for i in range(256):
        for _ in range(8):
            if i & 1:
                i >>= 1
                i ^= hash_poly
            else:
                i >>= 1
        hash_table.append(i)


def get_hash(data):
    if not hash_table:
        _init()

    h = 0
    for i in range(len(data)):
        h = ((h << 1 | h >> 63) ^ hash_table[data[i]]) & 0xffffffffffffffff
    return h
