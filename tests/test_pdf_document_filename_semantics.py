from product_intelligence.document_discovery import classify_document_candidate


def test_official_specsheet_filename_with_underscores_is_datasheet():
    url = (
        "https://www.jbl.es/on/demandware.static/-/Sites-masterCatalog_Harman/default/"
        "dw877faebf/pdfs/JBL_Quantum_350_Wireless_SpecSheet_Spanish.pdf"
    )

    assert classify_document_candidate(url, "", "") == "datasheet"
