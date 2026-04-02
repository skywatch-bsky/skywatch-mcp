# pattern: Functional Core

KNOWN_SHORTENERS = frozenset({
    "bit.ly",
    "bitly.com",
    "t.co",
    "goo.gl",
    "tinyurl.com",
    "ow.ly",
    "is.gd",
    "v.gd",
    "buff.ly",
    "amzn.to",
    "youtu.be",
    "rb.gy",
    "shorturl.at",
    "tiny.cc",
    "cutt.ly",
})


def is_known_shortener(hostname: str) -> bool:
    return hostname.lower() in KNOWN_SHORTENERS
