from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit

import requests

from .browser_search import browser_pdf_links, browser_search
from .discovery import SearchCandidate, _provider_search, _rank_candidates, search_web
from .models import ProductIdentity
from .normalize import key_norm
from .pdf_evidence import discover_pdf_candidates
from .web_fetch import UA

# Restoration is performed in the following git-object commit; this transient contents
# update only advances the branch so the exact prior blob can be restored atomically.
