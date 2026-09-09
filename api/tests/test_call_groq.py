from unittest.mock import patch, MagicMock
import ragcore


def test_empty_content_from_reasoning_model_gives_clear_message():
    """A reasoning model can spend its whole token budget thinking and
    return nothing visible -- this is exactly the bug we hit earlier;
    it should surface a real message, not silently return empty."""
    fake_response = MagicMock()
    fake_response.choices[0].message.content = ""
    fake_response.choices[0].finish_reason = "length"
    with patch.object(ragcore.groq_client.chat.completions, "create", return_value=fake_response):
        result = ragcore._call_groq("some-model", [{"role": "user", "content": "hi"}])
        assert "ran out of room" in result.lower()