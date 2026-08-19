from pathlib import Path

root = Path(__file__).parents[1]
workflow_path = root / 'src/product_intelligence/price_workflow.py'
trace_path = root / 'src/product_intelligence/price_trace.py'

workflow = workflow_path.read_text(encoding='utf-8')
if 'def _mercadolibre_terminal_status(' not in workflow:
    workflow = workflow.replace(
        'from .mercadolibre_oauth import build_mercadolibre_api_client\n',
        'from .mercadolibre_oauth import MercadoLibreAuthError, build_mercadolibre_api_client\n',
        1,
    )
    anchor = 'def _mercadolibre_queries(identity: ProductIdentity) -> list[str]:\n'
    helper = '''def _mercadolibre_terminal_status(exc: MercadoLibreAuthError) -> str:\n    code = str(getattr(exc, "code", "") or "").upper()\n    if code == "ML_AUTH_NOT_CONFIGURED":\n        return "ML_NOT_CONFIGURED"\n    if code in {"ML_REFRESH_TOKEN_INVALID", "ML_CLIENT_CREDENTIALS_INVALID", "ERROR_AUTH_MERCADOLIBRE"}:\n        return "ML_AUTH_FAILED"\n    return "ML_ACCESS_BLOCKED"\n\n\n'''
    if anchor not in workflow:
        raise SystemExit('mercadolibre query anchor not found')
    workflow = workflow.replace(anchor, helper + anchor, 1)
    old = '''    except Exception as exc:\n        trace.record("MercadoLibre", "FETCH_BLOCKED", detail=type(exc).__name__)\n        emit("source", channel="MercadoLibre", status="error", error=f"{type(exc).__name__}: {exc}")\n'''
    new = '''    except MercadoLibreAuthError as exc:\n        terminal = _mercadolibre_terminal_status(exc)\n        trace.record("MercadoLibre", terminal, detail=exc.code)\n        emit("source", channel="MercadoLibre", status="error", terminal=terminal, error_code=exc.code, error=str(exc))\n    except Exception as exc:\n        trace.record("MercadoLibre", "ML_ACCESS_BLOCKED", detail=type(exc).__name__)\n        emit("source", channel="MercadoLibre", status="error", terminal="ML_ACCESS_BLOCKED", error=f"{type(exc).__name__}: {exc}")\n'''
    if old not in workflow:
        raise SystemExit('mercadolibre catch block not found')
    workflow = workflow.replace(old, new, 1)
workflow_path.write_text(workflow, encoding='utf-8')

trace = trace_path.read_text(encoding='utf-8')
if '"ML_NOT_CONFIGURED": "ACCESS"' not in trace:
    trace = trace.replace(
        '    "FETCH_TIMEOUT": "ACCESS",\n',
        '    "FETCH_TIMEOUT": "ACCESS",\n    "ML_NOT_CONFIGURED": "ACCESS",\n    "ML_AUTH_FAILED": "ACCESS",\n    "ML_ACCESS_BLOCKED": "ACCESS",\n',
        1,
    )
trace_path.write_text(trace, encoding='utf-8')
print('P7_MERCADOLIBRE_SEMANTICS_PATCH=APPLIED')
