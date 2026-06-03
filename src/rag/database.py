from typing import List, Dict, Any

class MockRAGDatabase:
    """
    A mock implementation of a Retrieval-Augmented Generation (RAG) database.
    In a real scenario, this would connect to a vector database (e.g., Pinecone, Chroma) 
    containing medical literature, NCCN guidelines, and clinical trial data.
    """
    def __init__(self):
        """Initialize the Mock RAG Database connection."""
        self.connected = True
        print("[*] Mock RAG Database initialized.")

    def search_literature(self, gene: str, variant: str, cancer_context: str) -> List[Dict[str, Any]]:
        """
        Mock search for relevant medical literature.
        
        Args:
            gene (str): The gene symbol (e.g., 'EGFR').
            variant (str): The specific variant/mutation (e.g., 'L858R').
            cancer_context (str): The type of cancer (e.g., 'NSCLC').
            
        Returns:
            List[Dict[str, Any]]: A list of mock literature search results.
        """
        return [
            {
                "title": f"Targeted Therapy in {cancer_context} for {gene} {variant}",
                "snippet": f"Recent studies show significant efficacy of inhibitors targeting {gene} mutations, specifically {variant}.",
                "source": "Mock Oncology Journal, 2024"
            }
        ]

    def search_trials(self, gene: str, cancer_context: str) -> List[Dict[str, Any]]:
        """
        Mock search for clinical trials.
        
        Args:
            gene (str): The gene symbol (e.g., 'EGFR').
            cancer_context (str): The type of cancer (e.g., 'NSCLC').
            
        Returns:
            List[Dict[str, Any]]: A list of mock clinical trial results.
        """
        return [
            {
                "nct_id": f"NCT0000{abs(hash(gene)) % 10000:04d}",
                "title": f"Phase II Study of {gene} Inhibitor in {cancer_context}",
                "status": "Recruiting"
            }
        ]

def get_rag_context(gene: str, variant: str, cancer_context: str) -> str:
    """
    Helper function to fetch and format RAG context for the LLM prompt.
    
    This function retrieves relevant literature and clinical trial information
    from the RAG database and formats it into a string that can be easily
    injected into an LLM context window.
    
    Args:
        gene (str): The gene symbol.
        variant (str): The specific variant/mutation.
        cancer_context (str): The clinical context or cancer type.
        
    Returns:
        str: A formatted string containing retrieved literature and trials.
    """
    db = MockRAGDatabase()
    lit_results = db.search_literature(gene, variant, cancer_context)
    trial_results = db.search_trials(gene, cancer_context)
    
    context = "RAG Context:\n"
    context += "Literature:\n"
    for r in lit_results:
        context += f"- {r['title']} ({r['source']}): {r['snippet']}\n"
        
    context += "Clinical Trials:\n"
    for t in trial_results:
        context += f"- {t['nct_id']}: {t['title']} ({t['status']})\n"
        
    return context
