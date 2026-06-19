from app.tts.chunk import chunk_text, split_sentences


def test_split_basic():
    assert split_sentences("Hola. ¿Qué tal? ¡Bien!") == ["Hola.", "¿Qué tal?", "¡Bien!"]


def test_split_respects_abbreviation():
    # No debe partir tras "EE." ni "UU."
    assert split_sentences("Visitó EE. UU. ayer. Volvió.") == [
        "Visitó EE. UU. ayer.",
        "Volvió.",
    ]


def test_pack_chunks_groups():
    sentences = ["Frase uno.", "Frase dos.", "Frase tres."]
    text = " ".join(sentences)
    chunks = chunk_text(text, max_chars=20)
    assert all(len(c) <= 20 for c in chunks)
    assert " ".join(chunks).replace("  ", " ").count("Frase") == 3


def test_long_sentence_hard_split():
    long = "palabra " * 100  # 800 chars sin puntuación de frase
    chunks = chunk_text(long.strip(), max_chars=50)
    assert chunks
    assert all(len(c) <= 50 for c in chunks)
