from ingest import extract_captions


def test_detects_figure_caption():
    assert extract_captions("Figure 7: Comparison of accuracy.\nMore text.") == [("figure", 7)]


def test_detects_table_caption():
    assert extract_captions("Table 2. Dataset statistics.") == [("table", 2)]


def test_detects_abbreviated_fig():
    assert extract_captions("Fig. 3 shows the training loss curve.") == [("figure", 3)]


def test_ignores_mid_sentence_reference():
    """The whole point of anchoring to the start of a line -- a body
    sentence that just mentions a figure shouldn't be mistaken for its
    caption."""
    text = "As discussed, see Figure 2 above for the full comparison."
    assert extract_captions(text) == []


def test_multiple_captions_on_one_page():
    text = "Figure 1: First plot.\nSome body text.\nTable 1. Some stats."
    assert extract_captions(text) == [("figure", 1), ("table", 1)]