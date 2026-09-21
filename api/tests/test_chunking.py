from app.services.chunking_service import chunk_text, count_words


def _words(n: int, prefix: str = "word") -> str:
    """Build a paragraph of exactly n space-separated words."""
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_empty_string_produces_no_chunks():
    assert chunk_text("") == []


def test_whitespace_only_string_produces_no_chunks():
    assert chunk_text("   \n\n\t  \n  ") == []


def test_short_document_produces_one_chunk():
    text = "Employees receive 25 days of annual leave per year."
    chunks = chunk_text(text)
    assert chunks == [text]


def test_single_paragraph_below_target_is_one_chunk():
    paragraph = _words(300)
    chunks = chunk_text(paragraph, target_words=750, max_words=1000)
    assert len(chunks) == 1
    assert chunks[0] == paragraph


def test_several_paragraphs_combine_into_one_chunk_below_target():
    paragraphs = [_words(100, f"p{i}_") for i in range(5)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, target_words=750, max_words=1000)

    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_boundary_occurs_near_target_size():
    # Three 150-word paragraphs with target=350: the first two combine to
    # 300 words (still under target), but adding the third would reach 450
    # words, so it starts a new chunk instead.
    paragraphs = [_words(150, f"p{i}_") for i in range(3)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, target_words=350, max_words=1000)

    assert len(chunks) == 2
    assert chunks[0] == "\n\n".join(paragraphs[:2])
    assert chunks[1] == paragraphs[2]


def test_paragraph_order_is_preserved():
    paragraphs = [f"Paragraph {i}. " + _words(50, f"p{i}_") for i in range(6)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, target_words=120, max_words=300)

    # Reconstructing in chunk order should reproduce the paragraphs in
    # their original order.
    reconstructed = "\n\n".join(chunks)
    for earlier, later in zip(paragraphs, paragraphs[1:]):
        assert reconstructed.index(earlier) < reconstructed.index(later)


def test_final_short_chunk_is_retained():
    # 720 words nearly fills the 750-word target, so the trailing 50-word
    # paragraph can't be merged in and is kept as its own final chunk.
    long_paragraph = _words(720, "a0_")
    short_paragraph = _words(50, "a1_")
    text = long_paragraph + "\n\n" + short_paragraph

    chunks = chunk_text(text, target_words=750, max_words=1000)

    assert len(chunks) == 2
    assert chunks[-1] == short_paragraph
    assert count_words(chunks[-1]) == 50


def test_no_empty_chunks_are_produced():
    text = "\n\n".join(["Real paragraph one.", "", "   ", "Real paragraph two."])
    chunks = chunk_text(text)
    assert all(chunk.strip() for chunk in chunks)


def test_oversized_paragraph_with_sentences_is_split_on_sentence_boundaries():
    sentence_blob = ". ".join(f"This is sentence number {i}" for i in range(400)) + "."

    chunks = chunk_text(sentence_blob, target_words=100, max_words=150)

    assert len(chunks) > 1
    for chunk in chunks:
        assert count_words(chunk) <= 150


def test_oversized_paragraph_with_no_punctuation_falls_back_to_word_split():
    blob = _words(500)

    chunks = chunk_text(blob, target_words=100, max_words=150)

    assert len(chunks) == 5
    for chunk in chunks:
        assert count_words(chunk) == 100


def test_same_input_produces_same_output():
    paragraphs = [_words(200, f"p{i}_") for i in range(4)]
    text = "\n\n".join(paragraphs)

    first = chunk_text(text, target_words=300, max_words=500)
    second = chunk_text(text, target_words=300, max_words=500)

    assert first == second


def test_word_count_matches_chunk_contents():
    paragraph = _words(300)
    chunks = chunk_text(paragraph)
    assert count_words(chunks[0]) == 300


def test_no_words_are_lost_or_duplicated():
    paragraphs = [_words(50, "a_"), _words(2000, "b_"), _words(30, "c_")]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, target_words=750, max_words=1000)

    original_words = text.split()
    reconstructed_words = " ".join(chunks).split()
    assert reconstructed_words == original_words
