from app.retrieval import lexical_tsquery, rrf_fuse, select_top


def test_rrf_prefers_items_ranked_in_both_lists():
    scores = rrf_fuse([["a", "b", "c"], ["b", "d"]])
    ordered = sorted(scores, key=lambda cid: scores[cid], reverse=True)
    assert ordered[0] == "b"
    assert set(scores) == {"a", "b", "c", "d"}


def test_rrf_handles_empty_ranking():
    scores = rrf_fuse([["a"], []])
    assert list(scores) == ["a"]


def test_lexical_tsquery_keeps_product_names_and_numbers():
    query = lexical_tsquery(
        "Qual è il massimo potere schiarente di UAIT PASTE a 40 volumi?"
    )
    tokens = set(query.split(" | "))
    assert {"uait", "paste", "40", "volumi", "schiarente"} <= tokens
    assert "è" not in tokens  # too short to be meaningful


def test_lexical_tsquery_empty_for_no_tokens():
    assert lexical_tsquery("a e ...") is None


def test_select_top_caps_chunks_per_document():
    scores = {"docA#1": 0.9, "docA#2": 0.8, "docA#3": 0.7, "docB#1": 0.6, "docC#1": 0.5}
    assert select_top(scores, k=4, per_doc_cap=2) == [
        "docA#1",
        "docA#2",
        "docB#1",
        "docC#1",
    ]
    assert select_top(scores, k=4, per_doc_cap=0) == [
        "docA#1",
        "docA#2",
        "docA#3",
        "docB#1",
    ]


def test_select_top_collapses_identical_cross_doc_texts():
    scores = {"docA#1": 0.9, "docB#1": 0.8, "docC#1": 0.7}
    texts = {
        "docA#1": "16,00 euro\nPNH SERUM",
        "docB#1": "16,00  euro PNH SERUM",
        "docC#1": "altro",
    }
    assert select_top(scores, k=3, per_doc_cap=0, text_of=texts) == ["docA#1", "docC#1"]
