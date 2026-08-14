from product_intelligence.discovery import SearchCandidate
from product_intelligence.document_discovery import build_document_queries, discover_product_documents
from product_intelligence.models import ProductIdentity


def test_part_number_pdf_query_is_first_and_human_verifiable():
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", model="JBLQ350WLBLKAM")
    queries = build_document_queries(identity)
    assert queries[0] == "JBLQ350WLBLKAM pdf"
    assert '"JBLQ350WLBLKAM" pdf' in queries
    assert '"JBLQ350WLBLKAM" filetype:pdf' in queries


def test_document_discovery_uses_browser_when_http_returns_zero(monkeypatch):
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", model="JBLQ350WLBLKAM")
    monkeypatch.setattr(
        "product_intelligence.document_discovery._provider_search",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.browser_search",
        lambda query, **kwargs: [
            (
                "https://www.jbl.com/JBLQ350WLBLKAM.html",
                "JBL Quantum 350",
                "JBLQ350WLBLKAM Documents & Downloads",
            )
        ],
        raising=False,
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.resolve_document_candidate_urls",
        lambda identity, candidate, timeout=15, trace=None: [
            SearchCandidate(
                "https://support.jbl.com/JBLQ350WLBLKAM-spec.pdf",
                "Spec Sheet",
                "JBLQ350WLBLKAM specifications",
                .9,
                True,
            )
        ],
    )

    docs = discover_product_documents(identity, limit=4, timeout=1)
    assert docs
    assert docs[0].url.endswith(".pdf")


def test_document_discovery_runs_browser_pass_when_http_candidates_resolve_to_no_pdf(monkeypatch):
    identity = ProductIdentity(mpn="JBLQ350WLBLKAM", model="JBLQ350WLBLKAM")
    http_landing = (
        "https://example.com/JBLQ350WLBLKAM.html",
        "JBLQ350WLBLKAM product",
        "JBLQ350WLBLKAM support",
    )
    browser_pdf = (
        "https://support.jbl.com/JBLQ350WLBLKAM-spec.pdf",
        "JBLQ350WLBLKAM Spec Sheet",
        "JBLQ350WLBLKAM specifications",
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery._provider_search",
        lambda *args, **kwargs: [http_landing],
    )
    browser_calls = []
    monkeypatch.setattr(
        "product_intelligence.document_discovery.browser_search",
        lambda query, **kwargs: browser_calls.append(query) or [browser_pdf],
    )

    def resolve(identity, candidate, timeout=15, trace=None):
        if candidate.url.endswith(".pdf"):
            return [candidate]
        return []

    monkeypatch.setattr(
        "product_intelligence.document_discovery.resolve_document_candidate_urls",
        resolve,
    )
    monkeypatch.setattr(
        "product_intelligence.document_discovery.search_web",
        lambda *args, **kwargs: [],
    )

    docs = discover_product_documents(identity, limit=4, timeout=1)
    assert browser_calls, "Chromium fallback must run when HTTP pages yield zero concrete PDFs"
    assert [row.url for row in docs] == [browser_pdf[0]]
