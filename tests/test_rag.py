import pytest
from unittest.mock import patch, MagicMock
from ragcore import (
    extract_intent,
    _names_match,
    classify_node,
    QueryIntent,
)
from langgraph.graph import StateGraph  # if needed for state

# --- Test _names_match ---
def test_names_match_basic():
    source = "attention_is_all_you_need.pdf"
    assert _names_match(source, "attention is all you need") is True
    assert _names_match(source, "attention") is True
    assert _names_match(source, "transformer") is False

def test_names_match_case_insensitive():
    source = "BERT_paper.pdf"
    assert _names_match(source, "bert") is True
    assert _names_match(source, "BERT") is True

# --- Test extract_intent with mocked Groq ---
@patch('ragcore.groq_client.chat.completions.create')
def test_extract_intent_success(mock_groq):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"page_numbers": [3], "paper_names": [], "figure_number": null, "table_number": null, "is_comparison": false}'
    mock_groq.return_value = mock_response

    intent = extract_intent("What is on page 3?")
    assert intent.page_numbers == [3]
    assert intent.paper_names == []
    assert intent.figure_number is None
    assert intent.table_number is None
    assert intent.is_comparison is False

@patch('ragcore.groq_client.chat.completions.create')
def test_extract_intent_invalid_json_returns_default(mock_groq):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = 'not json'
    mock_groq.return_value = mock_response

    intent = extract_intent("some question")
    # Should return default QueryIntent (empty lists, None)
    assert intent.page_numbers == []
    assert intent.paper_names == []
    assert intent.figure_number is None

# --- Test classify_node routing ---
# We'll mock extract_intent and lookup_object_page to isolate routing logic
@patch('ragcore.lookup_object_page')
@patch('ragcore.extract_intent')
def test_classify_node_page_lookup(mock_extract, mock_lookup):
    # Setup intent: page number specified, single source available
    mock_extract.return_value = QueryIntent(page_numbers=[5], paper_names=[], figure_number=None, table_number=None, is_comparison=False)
    mock_lookup.return_value = 5  # lookup_object_page returns page number (if figure/table)
    state = {
        "query": "explain page 5",
        "sources": ["paper1.pdf"],
        "k": 5,
    }
    result = classify_node(state)
    assert result["route"] == "page_lookup"
    assert result["matched_source"] == "paper1.pdf"
    assert result["page_numbers"] == [5]

@patch('ragcore.extract_intent')
def test_classify_node_semantic(mock_extract):
    mock_extract.return_value = QueryIntent(page_numbers=[], paper_names=[], figure_number=None, table_number=None, is_comparison=False)
    state = {
        "query": "what is the main idea?",
        "sources": ["paper1.pdf", "paper2.pdf"],
        "k": 5,
    }
    result = classify_node(state)
    assert result["route"] == "semantic"

@patch('ragcore.extract_intent')
def test_classify_node_comparison(mock_extract):
    mock_extract.return_value = QueryIntent(
        page_numbers=[],
        paper_names=["paper1", "paper2"],
        figure_number=None,
        table_number=None,
        is_comparison=True
    )
    state = {
        "query": "compare paper1 and paper2",
        "sources": ["paper1.pdf", "paper2.pdf"],
        "k": 5,
    }
    result = classify_node(state)
    assert result["route"] == "multi_paper"
    assert set(result["matched_sources"]) == {"paper1.pdf", "paper2.pdf"}