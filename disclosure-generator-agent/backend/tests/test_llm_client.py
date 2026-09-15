from src.llm.client import _strip_reasoning


def test_strip_reasoning_balanced_think_tags():
    assert _strip_reasoning("<think>internal chatter, 500</think>Hello!") == "Hello!"


def test_strip_reasoning_leaked_unbalanced_closing_tag():
    # Observed with some Ollama/Qwen3 version combinations: the opening
    # <think> tag is consumed elsewhere but the closing marker leaks into
    # content along with the reasoning text before it.
    assert _strip_reasoning("some leaked reasoning text</think>\n\nHello!") == "Hello!"


def test_strip_reasoning_no_think_tags_passes_through():
    assert _strip_reasoning("Hello!") == "Hello!"


def test_strip_reasoning_trims_whitespace():
    assert _strip_reasoning("  Hello!  ") == "Hello!"
