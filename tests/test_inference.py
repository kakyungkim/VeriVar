import pandas as pd
from src.llm.inference import run_inference, _mock_inference

def test_mock_inference():
    df = pd.DataFrame([
        {"gene": "EGFR", "hgvsp": "p.L858R", "vaf": 0.5, "rule_based_tier": "Tier I"},
        {"gene": "TP53", "hgvsp": "p.R175H", "vaf": 0.3, "rule_based_tier": "Tier III"}
    ])
    
    res = _mock_inference(df, "rule", "NSCLC", "test_sample")
    
    assert res["sample_id"] == "test_sample"
    assert res["cancer_context"] == "NSCLC"
    assert len(res["variants"]) == 2
    
    egfr_var = res["variants"][0]
    assert egfr_var["gene"] == "EGFR"
    assert egfr_var["potential_tier"] == "Tier I"
    assert "RAG Context" in egfr_var["oncogenic_evidence"]
