"""
Unicode search index.

Replaces the old mock `database.py`. There is no SQLite file and nothing to
download: Python's stdlib `unicodedata` module already embeds the full Unicode
Character Database, so we build an in-memory index of every *named* codepoint
(~143,000) in about a quarter of a second at startup.
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

UCD_VERSION = unicodedata.unidata_version

# Categories we never want to surface: control chars, surrogates, private use,
# and unassigned codepoints. Format chars (Cf) are kept on purpose -- ZWJ and
# friends are genuinely useful to copy.
_SKIP_CATEGORIES = frozenset({"Cc", "Cs", "Co", "Cn"})

# Human-readable labels for the general category codes.
CATEGORY_LABELS = {
    "Lu": "Uppercase Letter", "Ll": "Lowercase Letter", "Lt": "Titlecase Letter",
    "Lm": "Modifier Letter", "Lo": "Other Letter", "Mn": "Nonspacing Mark",
    "Mc": "Spacing Mark", "Me": "Enclosing Mark", "Nd": "Decimal Number",
    "Nl": "Letter Number", "No": "Other Number", "Pc": "Connector Punctuation",
    "Pd": "Dash Punctuation", "Ps": "Open Punctuation", "Pe": "Close Punctuation",
    "Pi": "Initial Quote", "Pf": "Final Quote", "Po": "Other Punctuation",
    "Sm": "Math Symbol", "Sc": "Currency Symbol", "Sk": "Modifier Symbol",
    "So": "Other Symbol", "Zs": "Space Separator", "Zl": "Line Separator",
    "Zp": "Paragraph Separator", "Cf": "Format",
}

# Block table: (start, name). A block runs until the next entry's start.
# Trimmed to the blocks people actually search; everything else falls back to
# the nearest preceding entry or "Other".
_BLOCKS: Sequence[tuple] = (
    (0x0000, "Basic Latin"), (0x0080, "Latin-1 Supplement"),
    (0x0100, "Latin Extended-A"), (0x0180, "Latin Extended-B"),
    (0x0250, "IPA Extensions"), (0x02B0, "Spacing Modifier Letters"),
    (0x0300, "Combining Diacritical Marks"), (0x0370, "Greek and Coptic"),
    (0x0400, "Cyrillic"), (0x0500, "Cyrillic Supplement"), (0x0530, "Armenian"),
    (0x0590, "Hebrew"), (0x0600, "Arabic"), (0x0700, "Syriac"),
    (0x0900, "Devanagari"), (0x0980, "Bengali"), (0x0A00, "Gurmukhi"),
    (0x0B80, "Tamil"), (0x0E00, "Thai"), (0x1000, "Myanmar"),
    (0x10A0, "Georgian"), (0x1100, "Hangul Jamo"), (0x1200, "Ethiopic"),
    (0x13A0, "Cherokee"), (0x1680, "Ogham"), (0x16A0, "Runic"),
    (0x1E00, "Latin Extended Additional"), (0x1F00, "Greek Extended"),
    (0x2000, "General Punctuation"), (0x2070, "Superscripts and Subscripts"),
    (0x20A0, "Currency Symbols"), (0x2100, "Letterlike Symbols"),
    (0x2150, "Number Forms"), (0x2190, "Arrows"),
    (0x2200, "Mathematical Operators"), (0x2300, "Miscellaneous Technical"),
    (0x2400, "Control Pictures"), (0x2440, "OCR"),
    (0x2460, "Enclosed Alphanumerics"), (0x2500, "Box Drawing"),
    (0x2580, "Block Elements"), (0x25A0, "Geometric Shapes"),
    (0x2600, "Miscellaneous Symbols"), (0x2700, "Dingbats"),
    (0x27F0, "Supplemental Arrows-A"), (0x2800, "Braille Patterns"),
    (0x2900, "Supplemental Arrows-B"), (0x2A00, "Supplemental Math Operators"),
    (0x2B00, "Miscellaneous Symbols and Arrows"), (0x2E80, "CJK Radicals"),
    (0x3000, "CJK Symbols and Punctuation"), (0x3040, "Hiragana"),
    (0x30A0, "Katakana"), (0x3200, "Enclosed CJK"), (0x4E00, "CJK Unified Ideographs"),
    (0xA000, "Yi Syllables"), (0xA720, "Latin Extended-D"),
    (0xAC00, "Hangul Syllables"), (0xF900, "CJK Compatibility Ideographs"),
    (0xFB00, "Alphabetic Presentation Forms"), (0xFE00, "Variation Selectors"),
    (0xFE30, "CJK Compatibility Forms"), (0xFF00, "Halfwidth and Fullwidth Forms"),
    (0x10000, "Linear B"), (0x10330, "Gothic"), (0x10900, "Phoenician"),
    (0x12000, "Cuneiform"), (0x13000, "Egyptian Hieroglyphs"),
    (0x16800, "Bamum"), (0x1B000, "Kana Supplement"),
    (0x1D000, "Byzantine Musical Symbols"), (0x1D100, "Musical Symbols"),
    (0x1D400, "Mathematical Alphanumeric Symbols"),
    (0x1F000, "Mahjong Tiles"), (0x1F030, "Domino Tiles"),
    (0x1F0A0, "Playing Cards"), (0x1F100, "Enclosed Alphanumeric Supplement"),
    (0x1F300, "Miscellaneous Symbols and Pictographs"), (0x1F600, "Emoticons"),
    (0x1F650, "Ornamental Dingbats"), (0x1F680, "Transport and Map Symbols"),
    (0x1F700, "Alchemical Symbols"), (0x1F780, "Geometric Shapes Extended"),
    (0x1F800, "Supplemental Arrows-C"), (0x1F900, "Supplemental Symbols and Pictographs"),
    (0x1FA70, "Symbols and Pictographs Extended-A"),
    (0x20000, "CJK Extension B"), (0xE0000, "Tags"),
)
_BLOCK_STARTS = [b[0] for b in _BLOCKS]

# Blocks that everyday users mean 90% of the time. Used as a ranking boost so
# "heart" surfaces the emoji and the dingbat, not an obscure Egyptian glyph.
_POPULAR_BLOCKS = frozenset({
    "Basic Latin", "Latin-1 Supplement", "General Punctuation", "Currency Symbols",
    "Letterlike Symbols", "Arrows", "Mathematical Operators", "Geometric Shapes",
    "Miscellaneous Symbols", "Dingbats", "Emoticons", "Greek and Coptic",
    "Miscellaneous Symbols and Pictographs", "Supplemental Symbols and Pictographs",
    "Transport and Map Symbols", "Symbols and Pictographs Extended-A",
    "Box Drawing", "Superscripts and Subscripts", "Miscellaneous Technical",
})

# Huge, low-interest blocks that should never outrank a real name match.
_BULK_BLOCKS = frozenset({
    "CJK Unified Ideographs", "CJK Extension B", "Hangul Syllables",
    "CJK Compatibility Ideographs", "Yi Syllables", "Egyptian Hieroglyphs",
    "Cuneiform", "Braille Patterns", "Tags", "Variation Selectors",
})

# Query expansions: what people type -> words that appear in the official name.
SYNONYMS = {
    "tick": "check mark", "ticked": "check mark", "checkmark": "check mark",
    "cross": "multiplication x ballot", "x": "multiplication ballot",
    "lol": "face with tears of joy", "laugh": "face with tears of joy",
    "cry": "crying face", "smile": "smiling face", "sad": "frowning face",
    "shrug": "person shrugging", "thumbsup": "thumbs up", "fire": "fire",
    "tm": "trade mark", "(c)": "copyright", "(r)": "registered",
    "...": "horizontal ellipsis", "ellipsis": "horizontal ellipsis",
    "dash": "em dash en dash", "--": "em dash", "-": "hyphen dash",
    "->": "rightwards arrow", "<-": "leftwards arrow",
    "=>": "rightwards double arrow", "!=": "not equal", "/=": "not equal",
    "<=": "less-than or equal", ">=": "greater-than or equal",
    "+-": "plus-minus", "deg": "degree", "degrees": "degree",
    "euro": "euro sign", "pound": "pound sign", "yen": "yen sign",
    "cent": "cent sign", "bitcoin": "bitcoin sign",
    "space": "space", "nbsp": "no-break space", "zwj": "zero width joiner",
    "bullet": "bullet", "dot": "bullet middle dot",
    "star": "star", "heart": "heart", "arrow": "arrow", "infinity": "infinity",
    "half": "vulgar fraction one half", "quarter": "vulgar fraction one quarter",
    "alpha": "greek small letter alpha", "beta": "greek small letter beta",
    "pi": "greek small letter pi", "mu": "greek small letter mu",
    "lambda": "greek small letter lambda", "sigma": "greek capital letter sigma",
    "omega": "greek small letter omega", "delta": "greek capital letter delta",
    "sum": "n-ary summation", "product": "n-ary product", "root": "square root",
    "integral": "integral", "approx": "almost equal", "therefore": "therefore",
}

_HEX_RE = re.compile(r"^(?:u\+|u|0x|\\u|&#x)?([0-9a-f]{2,6});?$", re.IGNORECASE)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _block_for(cp: int) -> str:
    i = bisect_right(_BLOCK_STARTS, cp) - 1
    return _BLOCKS[i][1] if i >= 0 else "Other"


@dataclass(frozen=True, slots=True)
class Character:
    """A single named Unicode codepoint."""

    cp: int
    name: str
    category: str
    block: str

    @property
    def char(self) -> str:
        return chr(self.cp)

    @property
    def code(self) -> str:
        return f"U+{self.cp:04X}"

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)

    @property
    def python_escape(self) -> str:
        return f"\\U{self.cp:08X}" if self.cp > 0xFFFF else f"\\u{self.cp:04X}"

    @property
    def html_entity(self) -> str:
        return f"&#x{self.cp:X};"

    @property
    def utf8_bytes(self) -> str:
        return " ".join(f"{b:02X}" for b in self.char.encode("utf-8"))

    @property
    def is_printable(self) -> bool:
        """False for marks/format chars that render as nothing on their own."""
        return self.category not in {"Mn", "Mc", "Me", "Cf", "Zl", "Zp"}


class UnicodeIndex:
    """In-memory, offline index over every named codepoint."""

    def __init__(self, chars: Optional[List[Character]] = None) -> None:
        self._chars: List[Character] = chars if chars is not None else self._build()
        self._by_cp = {c.cp: c for c in self._chars}
        # token -> set of positions, for fast candidate narrowing on long queries
        self._token_map: dict = {}
        for idx, c in enumerate(self._chars):
            for tok in _TOKEN_RE.findall(c.name.lower()):
                self._token_map.setdefault(tok, []).append(idx)

    # ---------------------------------------------------------------- build

    @staticmethod
    def _build() -> List[Character]:
        chars: List[Character] = []
        append = chars.append
        name_of = unicodedata.name
        cat_of = unicodedata.category
        for cp in range(0x110000):
            ch = chr(cp)
            cat = cat_of(ch)
            if cat in _SKIP_CATEGORIES:
                continue
            try:
                name = name_of(ch)
            except ValueError:
                continue
            append(Character(cp, name, cat, _block_for(cp)))
        return chars

    def __len__(self) -> int:
        return len(self._chars)

    @property
    def blocks(self) -> List[str]:
        return sorted({c.block for c in self._chars})

    def get(self, cp: int) -> Optional[Character]:
        return self._by_cp.get(cp)

    # --------------------------------------------------------------- search

    def search(self, query: str, limit: int = 200,
               block: Optional[str] = None) -> List[Character]:
        """Ranked search. Empty query returns a useful starter set."""
        query = (query or "").strip()

        if not query:
            if block:
                return [c for c in self._chars if c.block == block][:limit]
            return [c for c in self._chars
                    if c.block in _POPULAR_BLOCKS and c.cp > 0x2000][:limit]

        best: dict = {}

        def offer(c: Character, score: int) -> None:
            """Keep the highest score seen for each codepoint."""
            if block and c.block != block:
                return
            prev = best.get(c.cp)
            if prev is None or score > prev[0]:
                best[c.cp] = (score, c)

        q = query.lower()

        # 1. Explicit codepoint reference -> exact lookup, nothing else.
        m = _HEX_RE.match(q)
        explicit = bool(re.match(r"^(u\+|0x|\\u|&#x)", q, re.IGNORECASE))
        if m:
            try:
                hit = self._by_cp.get(int(m.group(1), 16))
            except ValueError:
                hit = None
            if hit:
                offer(hit, 10_000)
                if explicit:
                    return [c for _, c in best.values()][:limit]

        # 2. The user pasted the character(s) themselves.
        if len(query) <= 8:
            for ch in query:
                hit = self._by_cp.get(ord(ch))
                if hit and (ord(ch) > 0x7F or len(query) == 1):
                    offer(hit, 9_000)

        # 3. Name search. A synonym is an ALTERNATIVE query, never merged into
        #    the original -- merging used to require every word from both,
        #    which made "tick" and "zwj" return nothing useful.
        variants = [q]
        if q in SYNONYMS:
            variants.append(SYNONYMS[q])

        for vi, variant in enumerate(variants):
            terms = _TOKEN_RE.findall(variant)
            if not terms:
                continue
            candidates = self._candidates(terms)
            if candidates is None:
                continue
            penalty = 0 if vi == 0 else 60  # prefer the literal query
            for idx in candidates:
                c = self._chars[idx]
                s = self._score(c, variant, terms)
                if s > 0:
                    offer(c, s - penalty)

        ranked = sorted(best.values(), key=lambda t: (-t[0], t[1].cp))
        return [c for _, c in ranked[:limit]]

    def _candidates(self, terms: Sequence[str]) -> Optional[Iterable[int]]:
        """Narrow to the rarest term's matches. None means 'no possible hits'."""
        best: Optional[set] = None
        for term in terms:
            hits: set = set()
            exact = self._token_map.get(term)
            if exact:
                hits.update(exact)
            # Prefix scan is the expensive part, so only pay for it when the
            # exact-token match is thin or missing.
            if len(term) >= 3 and len(hits) < 200:
                for tok, idxs in self._token_map.items():
                    if tok.startswith(term):
                        hits.update(idxs)
            if not hits:
                # Short terms may still match inside a token; long ones cannot,
                # so bail out instead of scanning all 143k names.
                if len(term) >= 3:
                    return None
                return range(len(self._chars))
            if best is None or len(hits) < len(best):
                best = hits
        return best if best is not None else range(len(self._chars))

    @staticmethod
    def _score(c: Character, q: str, terms: Sequence[str]) -> int:
        name = c.name.lower()
        name_tokens = _TOKEN_RE.findall(name)
        token_set = set(name_tokens)

        # Every term must match somehow; quality of each match is summed so a
        # prefix hit ("right" -> RIGHTWARDS) still competes with an exact one.
        total = 0
        for t in terms:
            if t in token_set:
                total += 1000
            elif any(nt.startswith(t) for nt in name_tokens):
                total += 880
            elif t in name:
                total += 500
            else:
                return 0
        score = total // len(terms)

        if name == q:
            score += 4_000
        elif name.startswith(q):
            score += 1_500
        if name_tokens[: len(terms)] == list(terms):
            score += 600

        score -= min(len(c.name), 90)
        if c.block in _POPULAR_BLOCKS:
            score += 250
        if c.block in _BULK_BLOCKS:
            score -= 900
        if c.cp <= 0xFFFF:
            score += 40
        return score


_SHARED: Optional[UnicodeIndex] = None


def shared_index() -> UnicodeIndex:
    """Process-wide singleton, so the index is only built once."""
    global _SHARED
    if _SHARED is None:
        _SHARED = UnicodeIndex()
    return _SHARED
