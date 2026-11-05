"""Hindi words (Devanagari) -> Hinglish (Roman letters), the way people type on WhatsApp.

    मैंने अपनी नौकरी छोड़ दी  ->  maine apni naukri chhod di

Works one word at a time, so every caption word keeps its own timing. No downloads, no AI:
a list of very common words, then simple spelling rules for the rest. Words that are already in
Roman letters (English, or a word the user typed) are left exactly as they are.

The rules, in short:
  - every consonant carries a hidden "a" (क = ka); it is dropped at the end of a word (कर = kar)
    and in the middle where Hindi speakers drop it (करना = karna, not karana);
  - long vowels are doubled only in a word's first syllable (आज = aaj, हमारी = hamari, था = tha).
"""
import re

CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    # with a dot below (nukta), either as one character or as letter + ़
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "फ़": "f", "ड़": "d", "ढ़": "dh", "य़": "y",
}
NUKTA_FORMS = {"क": "क़", "ख": "ख़", "ग": "ग़", "ज": "ज़", "फ": "फ़", "ड": "ड़", "ढ": "ढ़", "य": "य़"}
VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
          "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऑ": "o", "ऍ": "e"}
MATRAS = {"ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
          "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ॉ": "o", "ॅ": "e"}
WORD_END = {"aa": "a", "ee": "i", "oo": "u"}   # था = tha, थी = thi, तू = tu
VIRAMA, ANUSVARA, CHANDRABINDU, VISARGA, NUKTA = "्", "ं", "ँ", "ः", "़"
LABIALS = ("p", "f", "b", "bh", "m")          # ं before these sounds like m (संभव = sambhav)
OTHER = {"।": ".", "॥": ".", "ॐ": "om", **{chr(0x966 + d): str(d) for d in range(10)}}

# The words people say most, spelled the usual Hinglish way (rules alone get some of these wrong).
COMMON = {
    "है": "hai", "हैं": "hain", "हूँ": "hoon", "हूं": "hoon", "हो": "ho", "में": "mein",
    "मैं": "main", "मैंने": "maine", "नहीं": "nahi", "नही": "nahi", "क्या": "kya", "क्यों": "kyun",
    "क्यूँ": "kyun", "क्यूं": "kyun", "क्योंकि": "kyunki", "यह": "yeh", "ये": "ye", "वह": "woh",
    "वो": "wo", "और": "aur", "तो": "toh", "भी": "bhi", "के": "ke", "की": "ki", "का": "ka",
    "को": "ko", "से": "se", "पर": "par", "कि": "ki", "हम": "hum", "तुम": "tum", "आप": "aap",
    "मुझे": "mujhe", "तुझे": "tujhe", "उन्हें": "unhe", "हमें": "hume", "आज": "aaj", "अब": "ab",
    "सब": "sab", "कुछ": "kuch", "बहुत": "bahut", "बहोत": "bahut", "अच्छा": "accha", "अच्छी": "acchi",
    "अच्छे": "acche", "ठीक": "theek", "लेकिन": "lekin", "कैसे": "kaise", "कैसा": "kaisa",
    "कहाँ": "kahan", "कहां": "kahan", "यहाँ": "yahan", "यहां": "yahan", "वहाँ": "wahan",
    "वहां": "wahan", "हाँ": "haan", "हां": "haan", "माँ": "maa", "मां": "maa", "दोस्तों": "dosto",
    "दोस्तो": "dosto", "नमस्ते": "namaste", "नमस्कार": "namaskar", "धन्यवाद": "dhanyavaad",
    "लिए": "liye", "लिये": "liye", "चाहिए": "chahiye", "चाहिये": "chahiye", "जिंदगी": "zindagi",
    "ज़िंदगी": "zindagi", "ज़िन्दगी": "zindagi", "जिन्दगी": "zindagi", "प्यार": "pyaar",
    "लोगों": "logon", "वाले": "wale", "वाला": "wala", "वाली": "wali", "पहले": "pehle",
    "पहला": "pehla", "कहा": "kaha", "रहा": "raha", "रही": "rahi", "रहे": "rahe",
    "गया": "gaya", "गई": "gayi", "गए": "gaye", "दिया": "diya", "किया": "kiya", "हुआ": "hua",
    "हुई": "hui", "हुए": "hue", "इसलिए": "isliye", "मतलब": "matlab", "शायद": "shayad",
    "सच": "sach", "बस": "bas", "फिर": "phir", "एक": "ek", "दो": "do", "तीन": "teen",
    "बात": "baat", "समझ": "samajh", "वीडियो": "video", "विडियो": "video", "चैनल": "channel",
    "सब्सक्राइब": "subscribe", "लाइक": "like", "शेयर": "share", "कमेंट": "comment",
    "फोन": "phone", "फ़ोन": "phone", "ऑफिस": "office", "स्कूल": "school", "कॉलेज": "college",
    "जॉब": "job", "प्लान": "plan", "बिज़नेस": "business", "बिजनेस": "business",
}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    return bool(DEVANAGARI.search(text))


def _syllables(word: str) -> list[list] | None:
    """[[sound, vowel], ...] where vowel is "a" (the hidden one), a written vowel, or "" (none).
    Non-Hindi characters come through as [char, None]. None if the word has no letters."""
    out = []
    i = 0
    while i < len(word):
        ch = word[i]
        if i + 1 < len(word) and word[i + 1] == NUKTA and ch in NUKTA_FORMS:
            ch, i = NUKTA_FORMS[ch], i + 1
        if ch in CONSONANTS:
            out.append([CONSONANTS[ch], "a"])
        elif ch in VOWELS:
            out.append(["", VOWELS[ch]])
        elif ch in MATRAS and out and out[-1][1] is not None:
            out[-1][1] = MATRAS[ch]
        elif ch == VIRAMA and out and out[-1][0]:
            out[-1][1] = ""
        elif ch in (ANUSVARA, CHANDRABINDU) and out:
            out.append(["~", None])          # decided once we know the next sound
        elif ch == VISARGA:
            out.append(["h", None])
        elif ch == NUKTA:
            pass
        else:
            out.append([OTHER.get(ch, ch), None])
        i += 1
    return out


def _is_letter(syl) -> bool:
    return syl[1] is not None


def _drop_schwas(syls: list[list]) -> None:
    """Remove the hidden "a" where Hindi speakers do not say it (right to left, like the
    standard schwa-deletion rule: vowel + consonant + [a] + consonant + vowel)."""
    letters = [i for i, s in enumerate(syls) if _is_letter(s)]
    if not letters:
        return
    last = letters[-1]
    # End of a word: कर = kar. Kept after a joined pair (मित्र = mitra) and in one-letter words (न = na).
    if syls[last][1] == "a" and syls[last][0] and len(letters) > 1:
        prev = syls[letters[-2]]
        if prev[1] != "":
            syls[last][1] = ""
    for n in range(len(letters) - 2, 0, -1):
        i, before, after = letters[n], syls[letters[n - 1]], syls[letters[n + 1]]
        s = syls[i]
        nasal_after = lambda k: k + 1 < len(syls) and syls[k + 1][0] == "~"
        # kept after a syllable closed by a nasal: कंपनी = kampani
        if (s[1] == "a" and s[0] and before[1] and after[0] and after[1]
                and not nasal_after(i) and not nasal_after(letters[n - 1])):
            s[1] = ""


def _spell(syls: list[list]) -> str:
    letters = [i for i, s in enumerate(syls) if _is_letter(s)]
    last = letters[-1] if letters else -1
    first = next((i for i in letters if syls[i][1]), -1)    # first syllable that has a vowel
    out = []
    for i, (sound, vowel) in enumerate(syls):
        if sound == "~":          # nasal sound: m before p/b/m, otherwise n
            nxt = next((syls[j][0] for j in range(i + 1, len(syls)) if _is_letter(syls[j])), "")
            out.append("m" if nxt in LABIALS and nxt else "n")
            continue
        if vowel is None:
            out.append(sound)
            continue
        if i == last and vowel in WORD_END:
            vowel = WORD_END[vowel]
        elif i != first and vowel in ("aa", "ee"):
            vowel = WORD_END[vowel]
        if sound == "v" and i > 0 and syls[i - 1][1] == "":   # स्व = sw (swagat)
            sound = "w"
        out.append(sound + vowel)
    text = "".join(out)
    text = text.replace("chchh", "cch").replace("chch", "cch")   # अच्छा = accha
    return text


def romanize_word(word: str) -> str:
    """One word in Hinglish. Punctuation around it is kept (नहीं, -> nahi,)."""
    if not has_devanagari(word):
        return word
    # split off punctuation around the word (not the vowel signs: to Python those are not letters)
    m = re.fullmatch(r"([^\w\u0900-\u0963\u0966-\u097F]*)(.*?)([^\w\u0900-\u0963\u0966-\u097F]*)", word)
    lead, core, tail = m.groups()
    if core in COMMON:
        roman = COMMON[core]
    else:
        syls = _syllables(core)
        _drop_schwas(syls)
        roman = _spell(syls)
    tail = "".join(OTHER.get(c, c) for c in tail)
    return lead + roman + tail


def romanize(text: str) -> str:
    """A whole line, word by word."""
    return " ".join(romanize_word(w) for w in text.split(" "))


SCRIPTS = ("original", "hinglish")


def convert_words(words: list[dict], script: str) -> list[dict]:
    """Caption words in the chosen script. The words as Whisper heard them are kept under "orig",
    so switching back to the original script gives them back."""
    if script == "hinglish":
        return [{**w, "orig": w.get("orig", w["text"]), "text": romanize_word(w.get("orig", w["text"]))}
                for w in words]
    return [{**{k: v for k, v in w.items() if k != "orig"}, "text": w.get("orig", w["text"])}
            for w in words]
