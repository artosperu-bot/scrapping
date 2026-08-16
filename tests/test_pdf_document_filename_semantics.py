from product_intelligence.document_discovery import classify_document_candidate


def _official_specsheet_url():
    return (
        "https://www.jbl.es/on/demandware.static/-/Sites-masterCatalog_Harman/default/"
        "dw877faebf/pdfs/JBL_Quantum_350_Wireless_SpecSheet_Spanish.pdf"
    )


def test_official_specsheet_filename_with_underscores_is_datasheet():
    assert classify_document_candidate(_official_specsheet_url(), "", "") == "datasheet"


def test_technical_filename_is_not_vetoed_by_noisy_promotional_search_snippet():
    assert classify_document_candidate(
        _official_specsheet_url(),
        "JBL Quantum 350 Wireless Spec Sheet",
        "Shop catalog sale offers and product information",
    ) == "datasheet"
