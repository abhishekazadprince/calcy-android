from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "assets" / "fonts"
DEVANAGARI = BASE / "NotoSansDevanagari-Regular.ttf"
DEVANAGARI_BOLD = BASE / "NotoSansDevanagari-SemiBold.ttf"
LATIN = BASE / "NotoSans-Regular.ttf"
LATIN_BOLD = BASE / "NotoSans-Bold.ttf"
MATH = BASE / "DejaVuSans.ttf"
MATH_BOLD = BASE / "DejaVuSans-Bold.ttf"

# Characters for which the math face is intentionally preferred. Everything
# else in a mixed sentence stays in Noto Sans / Noto Sans Devanagari.
MATH_CHARS = set(
    "₀₁₂₃₄₅₆₇₈₉₊₋₍₎′″ωΩ∞→←↔∑∂√≤≥±×÷≈≠∫∈∇∝πθφψλμσ²³⁻¹"
    "αβγδεζηικξνρτχ"
)


def path(name: str) -> str:
    p = BASE / name
    return str(p) if p.exists() else "Roboto"


def is_devanagari_char(ch: str) -> bool:
    return "\u0900" <= ch <= "\u097f"


def is_devanagari(text: str) -> bool:
    return any(is_devanagari_char(ch) for ch in text)


def is_math_char(ch: str) -> bool:
    return ch in MATH_CHARS or ("\u2070" <= ch <= "\u209f")


def is_math_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if any(is_math_char(ch) for ch in stripped):
        return True
    if any(tok in stripped for tok in ("y1", "y2", "y3", "y16", "x''", "=", ";", "f1", "f2")):
        return not is_devanagari(stripped)
    return False


def iter_font_runs(text: str, bold: bool = False):
    """Yield (kind, text, font_path) runs without breaking Devanagari clusters."""
    dev = DEVANAGARI_BOLD if bold and DEVANAGARI_BOLD.exists() else DEVANAGARI
    latin = LATIN_BOLD if bold and LATIN_BOLD.exists() else LATIN
    math = MATH_BOLD if bold and MATH_BOLD.exists() else MATH

    current_kind = None
    current = []

    def kind(ch: str) -> str:
        if is_devanagari_char(ch):
            return "dev"
        if is_math_char(ch):
            return "math"
        return "latin"

    for ch in text:
        k = kind(ch)
        if current_kind is None:
            current_kind = k
        if k != current_kind:
            s = "".join(current)
            if s:
                font = dev if current_kind == "dev" else math if current_kind == "math" else latin
                yield current_kind, s, str(font)
            current = []
            current_kind = k
        current.append(ch)

    if current:
        s = "".join(current)
        font = dev if current_kind == "dev" else math if current_kind == "math" else latin
        yield current_kind, s, str(font)


def manual_markup(text: str, bold: bool = False) -> str:
    """Kivy markup with explicit Devanagari/Latin/math font runs."""
    def escape(s: str) -> str:
        return s.replace("&", "&amp;").replace("[", "&#91;").replace("]", "&#93;")

    return "".join(
        f"[font={font}]{escape(run)}[/font]"
        for _kind, run, font in iter_font_runs(text, bold=bold)
    )
