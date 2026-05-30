from src.rag.database import get_rag_context, MockRAGDatabase

def test_rag_database_literature():
    db = MockRAGDatabase()
    res = db.search_literature("EGFR", "L858R", "NSCLC")
    assert len(res) > 0
    assert "EGFR" in res[0]["title"]
    assert "L858R" in res[0]["snippet"]

def test_rag_database_trials():
    db = MockRAGDatabase()
    res = db.search_trials("KRAS", "NSCLC")
    assert len(res) > 0
    assert "KRAS" in res[0]["title"]

def test_get_rag_context():
    context = get_rag_context("TP53", "R175H", "NSCLC")
    assert "TP53" in context
    assert "R175H" in context
    assert "Literature:" in context
    assert "Clinical Trials:" in context
