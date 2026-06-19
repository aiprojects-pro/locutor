from app.tts.normalize import TextNormalizer, number_to_words

RULES = {
    "abbreviations": {"Sr.": "señor", "Dra.": "doctora"},
    "word_replacements": {"etc": "etcétera"},
    "punctuation": {"parentheses_to_commas": True, "collapse_repeated": True},
    "numbers": {
        "currency_symbol": "€", "currency_singular": "euro", "currency_plural": "euros",
        "cents_singular": "céntimo", "cents_plural": "céntimos",
    },
}
N = TextNormalizer(RULES)


def test_number_basic():
    assert number_to_words("1.991,50") == "mil novecientos noventa y uno coma cincuenta"


def test_number_integer():
    assert number_to_words("1234") == "mil doscientos treinta y cuatro"


def test_decimal_leading_zeros():
    # '0050' decimal -> 'cero cero cincuenta'
    assert number_to_words("3,0050") == "tres coma cero cero cincuenta"


def test_negative():
    assert N.normalize("-5") == "menos cinco"


def test_percent():
    assert N.normalize("50%") == "cincuenta por ciento"
    assert N.normalize("12,5%") == "doce coma cinco por ciento"


def test_currency_singular():
    assert N.normalize("1€") == "un euro"


def test_currency_plural():
    assert N.normalize("200€") == "doscientos euros"


def test_currency_with_cents():
    assert N.normalize("1,50€") == "un euro con cincuenta céntimos"


def test_currency_one_cent():
    assert N.normalize("2,01€") == "dos euros con un céntimo"


def test_abbreviations():
    assert N.normalize("Sr. Pérez") == "señor Pérez"


def test_word_replacement():
    assert N.normalize("uno, dos, etc") == "uno, dos, etcétera"


def test_parentheses_to_commas():
    out = N.normalize("Hola (mundo) hoy")
    assert "(" not in out and ")" not in out


def test_preserves_surrounding_spaces():
    # No debe pegar palabras alrededor de números/moneda/porcentaje.
    out = N.normalize("El total es 1.991,50€ es decir 200€ y el 50% hoy")
    assert out == (
        "El total es mil novecientos noventa y un euros con cincuenta céntimos "
        "es decir doscientos euros y el cincuenta por ciento hoy"
    )


def test_number_in_sentence():
    assert N.normalize("Hay 1.991,50 unidades") == "Hay mil novecientos noventa y uno coma cincuenta unidades"
