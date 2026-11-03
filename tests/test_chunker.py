from backend.pipeline.chunker import Chunker


def run(pieces: list[str]) -> list[str]:
    c = Chunker()
    out = [chunk for p in pieces for chunk in c.feed(p)]
    if rest := c.flush():
        out.append(rest)
    return out


def test_first_chunk_cuts_at_first_punctuation_with_two_words():
    text = "Oh, you went to the gym yesterday? Nice! What did you do?"
    assert run([text]) == ["Oh, you went to the gym yesterday?", "Nice!", "What did you do?"]


def test_first_chunk_cuts_after_six_words_without_punctuation():
    text = "That is a really cool detail to focus on. Tell me more."
    assert run([text]) == ["That is a really cool detail", "to focus on.", "Tell me more."]


def test_streamed_tokens_give_same_chunks():
    text = "That's great! How long have you been working there? Do you like it?"
    tokens = [text[i:i + 3] for i in range(0, len(text), 3)]
    assert run(tokens) == run([text])


def test_decimals_do_not_split():
    assert run(["It costs 2.5 dollars, more or less. Cheap!"]) == [
        "It costs 2.5 dollars,", "more or less.", "Cheap!"]
