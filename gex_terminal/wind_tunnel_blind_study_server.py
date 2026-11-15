"""Loopback interface for a synthetic or saved Blind Replay Study."""

import asyncio
from importlib.resources import files
import secrets

from aiohttp import web

from . import wind_tunnel_blind_saved_study_comparison as cohort_comparison
from . import wind_tunnel_blind_study_comparison as market_comparison
from .wind_tunnel_blind_saved_study import capture_ids, capture_market
from .wind_tunnel_blind_study import BlindStudyError
from .wind_tunnel_server import (
    BLIND_SAVED_STUDY, BLIND_STUDY, ID_PATTERN, MAX_JSON_BYTES, ORIGIN_KEY, TOKEN_KEY,
    ReceiptError, ReceiptStore, assemble_receipt, canonical_bytes, read_body,
    reproduce_receipt, run_bounded, security_boundary, validate_name,
)


def create_study_app(workspace, *, origin: str, study=None, studies=None, pair=None) -> web.Application:
    if sum(value is not None for value in (study, studies, pair)) != 1:
        raise ValueError("Specify one study, a set of market-bound studies, or a saved study pair.")
    if pair is not None:
        keys = cohort_comparison.SIDES
        if (set(pair) != set(keys)
                or any(item.symbol not in market_comparison.MARKETS or item.operation != BLIND_SAVED_STUDY
                       for item in pair.values())):
            raise ValueError("Choose a saved ES or NQ study for each of Study A and Study B.")
        if not pair["a"].capture_paths.keys().isdisjoint(pair["b"].capture_paths):
            raise ValueError("Choose distinct captures across Study A and Study B.")
        studies = dict(pair)
        comparison = cohort_comparison
        source_query = "slot"
    else:
        if study is not None:
            studies = {study.symbol: study}
        studies = dict(studies)
        if not studies or any(symbol not in market_comparison.MARKETS or item.symbol != symbol
                              or item.operation not in (BLIND_STUDY, BLIND_SAVED_STUDY)
                              for symbol, item in studies.items()):
            raise ValueError("Blind studies must be bound to their selected ES or NQ market.")
        if len(studies) > 1 and any(item.operation != BLIND_SAVED_STUDY for item in studies.values()):
            raise ValueError("A two-market study window requires saved studies for both markets.")
        keys = tuple(symbol for symbol in market_comparison.MARKETS if symbol in studies)
        comparison = market_comparison
        source_query = "symbol"
    locks = {key: asyncio.Lock() for key in keys}
    symbols = list(dict.fromkeys(studies[key].symbol for key in keys))
    comparison_receipts = {}

    app = web.Application(middlewares=[security_boundary], client_max_size=MAX_JSON_BYTES)
    app[ORIGIN_KEY] = origin
    app[TOKEN_KEY] = secrets.token_urlsafe(32)

    root = files("gex_terminal").joinpath("wind_tunnel_web")
    assets = {route: (root.joinpath(name).read_bytes(), mime) for route, (name, mime) in {
        "/": ("study.html", "text/html"),
        "/static/study.js": ("study.js", "text/javascript"),
        "/static/app.css": ("app.css", "text/css"),
        "/static/vendor/plotly.min.js": ("vendor/plotly.min.js", "text/javascript"),
        **{f"/static/icons/{name}.svg": (f"icons/{name}.svg", "image/svg+xml")
           for name in ("folder-open", "floppy-disk", "x")},
    }.items()}

    async def asset(request):
        data, mime = assets[request.path]
        return web.Response(body=data, content_type=mime)

    def study_key(request):
        selected = request.query.getall(source_query, ())
        if not selected and len(keys) == 1 and not request.query:
            return keys[0]
        if len(selected) == 1 and selected[0] in studies and len(request.query) == 1:
            return selected[0]
        if pair is not None:
            raise ReceiptError("Select Study A or Study B for this blind study.")
        raise ReceiptError("Select one saved market for this blind study.")

    async def perform(request, operation, *selected):
        async def action():
            try:
                return await operation()
            except BlindStudyError as exc:
                raise ReceiptError(str(exc)) from exc
        kind = comparison.OPERATION if len(selected) == 2 else studies[selected[0]].operation
        return await run_bounded(request, action, kind=kind, locks=tuple(locks[key] for key in selected))

    async def sources(_):
        payload = {"symbols": symbols}
        if pair is not None:
            payload["slots"] = [{"id": key, "symbol": studies[key].symbol} for key in keys]
        return web.json_response(payload)

    async def status(request):
        key = study_key(request)
        return await perform(request, studies[key].status, key)

    async def submit(request):
        key = study_key(request)
        body = await read_body(request)
        if set(body) != {"calls"}:
            raise ReceiptError("Supply the complete set of study calls.")

        async def action():
            return {"result": await studies[key].submit(body["calls"])}
        return await perform(request, action, key)

    async def save(request):
        key = study_key(request)
        study = studies[key]
        body = await read_body(request)
        if set(body) != {"name"}:
            raise ReceiptError("Supply only the study receipt name.")
        name = validate_name(body["name"])

        async def action():
            if study.result is None:
                raise ReceiptError("Submit every call and reveal the result before saving the study.")
            if study.receipt_id is not None:
                return store.load(study.receipt_id)
            receipt = store.save(assemble_receipt(name, study.operation, study.result))
            study.receipt_id = receipt["receipt_sha256"]
            return receipt
        return await perform(request, action, key)

    def matches_study(study, receipt):
        if receipt["kind"] != study.operation:
            return False
        if study.operation == BLIND_STUDY:
            return True
        try:
            selection = receipt["request"]
            return capture_market(selection) == study.symbol and set(capture_ids(selection)) == study.capture_paths.keys()
        except BlindStudyError:
            return False

    def receipt_metadata(matches, revealed):
        # A title can spoil the outcome of a study that has not been submitted.
        fields = ("id", "kind", "created_at", "name") if revealed else ("id", "kind", "created_at")
        rows = store.list(matches=matches)
        return web.json_response({"receipts": [{key: row[key] for key in fields} for row in rows]})

    async def receipts(request):
        study = studies[study_key(request)]
        return receipt_metadata(lambda receipt: matches_study(study, receipt), study.result is not None)

    async def reopen(request):
        key = study_key(request)
        study = studies[key]
        body = await read_body(request)
        receipt_id = body.get("id")
        if set(body) != {"id"} or not isinstance(receipt_id, str) or not ID_PATTERN.fullmatch(receipt_id):
            raise ReceiptError("Choose a saved study receipt to reopen.")

        async def action():
            receipt = store.load(receipt_id)
            if not matches_study(study, receipt):
                raise ReceiptError("Choose a receipt for the study's original captures.")
            study_captures = study.capture_paths if study.operation == BLIND_SAVED_STUDY else None
            verified = await reproduce_receipt(receipt, study_captures=study_captures)
            if verified["status"] != "verified":
                raise ReceiptError("The saved study did not reproduce exactly.")
            result = verified["result"]
            study.restore(result, receipt_id)
            return {"result": result, "receipt_sha256": receipt_id, "name": receipt["name"]}
        return await perform(request, action, key)

    def export_saved(receipt_id, label):
        receipt = store.load(receipt_id)
        return web.Response(body=canonical_bytes(receipt), content_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="wind-tunnel-{label}-{receipt_id[:12]}.json"',
        })

    async def export(request):
        study = studies[study_key(request)]
        receipt_id = request.match_info["id"]
        if study.result is None or study.receipt_id != receipt_id:
            raise ReceiptError("Save or reopen the study before exporting its receipt.")
        return export_saved(receipt_id, "study")

    def require_pair(request):
        if len(keys) != 2 or request.query:
            raise ReceiptError("Open two saved studies for a comparison.")

    def comparison_key():
        if all(study.result is not None for study in studies.values()):
            # Older ES proof envelopes can share the same exact commitment.
            return tuple(studies[key].result["request_sha256"] for key in keys)
        return None

    def matches_comparison(receipt):
        if receipt["kind"] != comparison.OPERATION:
            return False
        try:
            selection = comparison.normalize_request(receipt["request"])
            return all(capture_market(selection[key.lower()]) == studies[key].symbol
                       and set(capture_ids(selection[key.lower()])) == studies[key].capture_paths.keys()
                       for key in keys)
        except BlindStudyError:
            return False

    async def comparison_status(request):
        require_pair(request)
        return web.json_response({"receipt_sha256": comparison_receipts.get(comparison_key())})

    async def save_comparison(request):
        require_pair(request)
        body = await read_body(request)
        if set(body) != {"name"}:
            raise ReceiptError("Supply only the comparison receipt name.")
        name = validate_name(body["name"])

        async def action():
            key = comparison_key()
            if key is None:
                raise ReceiptError("Submit and reveal both studies before saving a comparison.")
            previous = comparison_receipts.get(key)
            if previous is not None:
                return store.load(previous)
            result = comparison.assemble_result(*(studies[side].result for side in keys))
            receipt = store.save(assemble_receipt(name, comparison.OPERATION, result))
            comparison_receipts[key] = receipt["receipt_sha256"]
            return receipt
        return await perform(request, action, *keys)

    async def list_comparisons(request):
        require_pair(request)
        return receipt_metadata(matches_comparison, comparison_key() is not None)

    async def reopen_comparison(request):
        require_pair(request)
        body = await read_body(request)
        receipt_id = body.get("id")
        if set(body) != {"id"} or not isinstance(receipt_id, str) or not ID_PATTERN.fullmatch(receipt_id):
            raise ReceiptError("Choose a saved study comparison receipt to reopen.")

        async def action():
            receipt = store.load(receipt_id)
            if not matches_comparison(receipt):
                raise ReceiptError("Choose a comparison receipt for both original capture sets.")
            captures = {key: studies[key].capture_paths for key in keys}
            verified = await reproduce_receipt(receipt, study_captures=captures)
            if verified["status"] != "verified":
                raise ReceiptError("The saved comparison did not reproduce exactly.")
            result = verified["result"]
            for key in keys:
                study = studies[key]
                child = result[key.lower()]
                if study.receipt_id is None or study.result["request_sha256"] != child["request_sha256"]:
                    study.restore(child, None)
            comparison_receipts[comparison_key()] = receipt_id
            return {"result": result, "receipt_sha256": receipt_id, "name": receipt["name"]}
        return await perform(request, action, *keys)

    async def export_comparison(request):
        require_pair(request)
        receipt_id = request.match_info["id"]
        if comparison_receipts.get(comparison_key()) != receipt_id:
            raise ReceiptError("Save or reopen the comparison before exporting its receipt.")
        return export_saved(receipt_id, "study-comparison")

    async def cleanup(_):
        store.close()
        for study in studies.values():
            study.close()

    for route in assets:
        app.router.add_get(route, asset)
    app.router.add_get("/api/blind-study", status)
    app.router.add_get("/api/blind-study/sources", sources)
    app.router.add_post("/api/blind-study/submit", submit)
    app.router.add_post("/api/blind-study/save", save)
    app.router.add_get("/api/blind-study/receipts", receipts)
    app.router.add_post("/api/blind-study/reopen", reopen)
    app.router.add_get("/api/blind-study/receipts/{id}/export", export)
    app.router.add_get("/api/blind-study/comparison", comparison_status)
    app.router.add_post("/api/blind-study/comparison/save", save_comparison)
    app.router.add_get("/api/blind-study/comparison/receipts", list_comparisons)
    app.router.add_post("/api/blind-study/comparison/reopen", reopen_comparison)
    app.router.add_get("/api/blind-study/comparison/receipts/{id}/export", export_comparison)
    app.on_cleanup.append(cleanup)
    store = ReceiptStore(workspace)
    return app
