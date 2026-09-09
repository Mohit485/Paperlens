from unittest.mock import patch
from ragcore import classify_node, QueryIntent


def _state(query="q", sources=None):
    return {"query": query, "sources": sources or ["paper1.pdf"], "history": []}


@patch("ragcore.extract_intent")
def test_routes_to_semantic_by_default(mock_extract):
    mock_extract.return_value = QueryIntent()
    assert classify_node(_state())["route"] == "semantic"


@patch("ragcore.extract_intent")
def test_page_lookup_single_paper(mock_extract):
    mock_extract.return_value = QueryIntent(page_numbers=[4])
    result = classify_node(_state(sources=["paper1.pdf"]))
    assert result["route"] == "page_lookup"
    assert result["matched_source"] == "paper1.pdf"


@patch("ragcore.extract_intent")
def test_ambiguous_when_page_named_but_multiple_papers(mock_extract):
    mock_extract.return_value = QueryIntent(page_numbers=[4])
    result = classify_node(_state(sources=["paper1.pdf", "paper2.pdf"]))
    assert result["route"] == "ambiguous"


@patch("ragcore.extract_intent")
def test_naming_two_papers_without_comparison_intent_is_not_multi_paper(mock_extract):
    """The actual refinement over the old regex version -- naming two
    papers isn't enough on its own, the question has to actually be a
    comparison."""
    mock_extract.return_value = QueryIntent(paper_names=["paper1", "paper2"], is_comparison=False)
    assert classify_node(_state(sources=["paper1.pdf", "paper2.pdf"]))["route"] != "multi_paper"


@patch("ragcore.extract_intent")
def test_multi_paper_when_both_signals_present(mock_extract):
    mock_extract.return_value = QueryIntent(paper_names=["paper1", "paper2"], is_comparison=True)
    result = classify_node(_state(sources=["paper1.pdf", "paper2.pdf"]))
    assert result["route"] == "multi_paper"
    assert set(result["matched_sources"]) == {"paper1.pdf", "paper2.pdf"}


@patch("ragcore.lookup_object_page")
@patch("ragcore.extract_intent")
def test_figure_reference_resolves_through_registry(mock_extract, mock_lookup):
    mock_extract.return_value = QueryIntent(figure_number=7)
    mock_lookup.return_value = 12
    result = classify_node(_state(sources=["paper1.pdf"]))
    assert result["route"] == "page_lookup"
    assert result["page_numbers"] == [12]


@patch("ragcore.lookup_object_page")
@patch("ragcore.extract_intent")
def test_figure_reference_falls_back_to_semantic_when_registry_misses(mock_extract, mock_lookup):
    mock_extract.return_value = QueryIntent(figure_number=99)
    mock_lookup.return_value = None
    assert classify_node(_state())["route"] == "semantic"