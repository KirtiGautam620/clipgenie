import pytest

from app import captionstyles
from app.hinglish import convert_words, romanize, romanize_word


@pytest.mark.parametrize("hindi, hinglish", [
    ("मैंने अपनी नौकरी छोड़ दी", "maine apni naukri chhod di"),
    ("आज के वीडियो में आपका स्वागत है", "aaj ke video mein aapka swaagat hai"),
    ("करना समझना बदलना", "karna samajhna badalna"),     # the hidden "a" dropped where unsaid
    ("मित्र कंपनी संभव", "mitra kampani sambhav"),
    ("हमारी सफलता", "hamari safalta"),
    ("अच्छा", "accha"),
])
def test_romanize(hindi, hinglish):
    assert romanize(hindi) == hinglish


def test_punctuation_and_latin_are_kept():
    assert romanize_word("नहीं,") == "nahi,"
    assert romanize_word("के।") == "ke."
    assert romanize_word('"सच?"') == '"sach?"'
    assert romanize_word("Python") == "Python"


def test_convert_words_round_trip():
    words = [{"text": "आज", "start": 0.0, "end": 0.3}, {"text": "OK", "start": 0.4, "end": 0.6}]
    roman = convert_words(words, "hinglish")
    assert [w["text"] for w in roman] == ["aaj", "OK"]
    assert roman[0]["start"] == 0.0 and roman[0]["orig"] == "आज"
    assert convert_words(roman, "original") == words


def test_style_accepts_only_known_scripts():
    assert captionstyles.resolve("clean", {"script": "hinglish"}).script == "hinglish"
    assert captionstyles.resolve("clean").script == "original"
    with pytest.raises(ValueError):
        captionstyles.resolve("clean", {"script": "klingon"})
