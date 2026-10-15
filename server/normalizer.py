"""
Arabic-aware text normalization for quote verification.

Normalization steps (from spec.md Component 5):
1. Strip Arabic diacritics (tashkeel)
2. Unify Alef variants → ا
3. Unify Ya: ي ↔ ى → ي
4. Unify Ta Marbuta / Ha: ة → ه
5. Lowercase Latin letters
6. Strip punctuation (Unicode punctuation categories)
7. Collapse whitespace → single space; strip leading/trailing
"""

import re
import unicodedata


# Unicode ranges for Arabic diacritics (tashkeel)
_DIACRITICS_RE = re.compile(
    '[\u0610-\u061A\u064B-\u065F\u0670]'
)

# Alef variants → bare Alef
_ALEF_MAP = str.maketrans({
    '\u0625': '\u0627',  # إ → ا
    '\u0623': '\u0627',  # أ → ا
    '\u0622': '\u0627',  # آ → ا
    '\u0671': '\u0627',  # ٱ → ا
})

# Ya unification: ى → ي
_YA_MAP = str.maketrans({
    '\u0649': '\u064A',  # ى → ي
})

# Ta Marbuta → Ha
_TA_MARBUTA_MAP = str.maketrans({
    '\u0629': '\u0647',  # ة → ه
})


def normalize_arabic(text: str) -> str:
    """
    Apply full Arabic-aware normalization pipeline to a text string.
    Returns a lowercased, diacritics-stripped, whitespace-collapsed string
    suitable for substring comparison.
    """
    if not text:
        return ""

    # 1. Strip Arabic diacritics
    s = _DIACRITICS_RE.sub('', text)

    # 2. Unify Alef variants
    s = s.translate(_ALEF_MAP)

    # 3. Unify Ya
    s = s.translate(_YA_MAP)

    # 4. Unify Ta Marbuta → Ha
    s = s.translate(_TA_MARBUTA_MAP)

    # 5. Lowercase Latin letters
    s = s.lower()

    # 6. Strip punctuation (Unicode categories P*)
    s = ''.join(
        ch for ch in s
        if not unicodedata.category(ch).startswith('P')
    )

    # 7. Collapse whitespace
    s = ' '.join(s.split())

    return s
