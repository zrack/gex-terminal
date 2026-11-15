"""A loopback app for blind reviews of explicitly selected saved captures."""

import asyncio
from importlib.resources import files
import secrets

from aiohttp import web

from . import wind_tunnel_blind_comparison as mixed_comparison
from . import wind_tunnel_blind_session_comparison as session_comparison
from .wind_tunnel_blind_review import BlindReviewError
from .wind_tunnel_server import (
    BLIND_COMPARISON, BLIND_REVIEW, BLIND_SESSION_COMPARISON, ID_PATTERN, MAX_JSON_BYTES, ORIGIN_KEY, TOKEN_KEY,
    ReceiptError, ReceiptStore, assemble_receipt, canonical_bytes, read_body,
    reproduce_receipt, run_bounded, security_boundary, validate_name,
)
from .wind_tunnel_sources import saved_capture_digest


def create_blind_app(workspace, *, origin: str, review=None, reviews=None, token: str | None = None) -> web.Application:
    if review is not None:
        if reviews is not None:
            raise ValueError("Specify one blind review or a set of market-bound reviews.")
        reviews = {review.replay.symbol: review}
    reviews = dict(reviews or {})
    same_market = reviews.keys() == set(session_comparison.SIDES)
    if same_market:
        symbols = {item.replay.symbol for item in reviews.values()}
        known = [item.replay.capture_sha256 for item in reviews.values() if item.replay.capture_sha256 is not None]
        if (len(symbols) != 1 or not symbols <= set(mixed_comparison.MARKETS)
                or len({item.replay for item in reviews.values()}) != 2 or len(set(known)) != len(known)):
            raise ValueError("Open two distinct saved sessions of the same market.")
    elif not reviews or any(key not in mixed_comparison.MARKETS or item.replay.symbol != key
                            for key, item in reviews.items()):
        raise ValueError("Blind reviews must be bound to their saved ES or NQ capture.")

    app = web.Application(middlewares=[security_boundary], client_max_size=MAX_JSON_BYTES)
    app[ORIGIN_KEY] = origin
    app[TOKEN_KEY] = token or secrets.token_urlsafe(32)
    locks = {item: asyncio.Lock() for item in reviews.values()}
    pair_order = session_comparison.SIDES if same_market else mixed_comparison.MARKETS
    paired = tuple(reviews[slot] for slot in pair_order if slot in reviews)
    comparison = session_comparison if same_market else mixed_comparison
    pair_kind = BLIND_SESSION_COMPARISON if same_market else BLIND_COMPARISON
    comparison_receipts = {}

    root = files("gex_terminal").joinpath("wind_tunnel_web")
    assets = {route: (root.joinpath(name).read_bytes(), mime) for route, (name, mime) in {
        "/": ("blind.html", "text/html"),
        "/static/blind.js": ("blind.js", "text/javascript"),
        "/static/app.css": ("app.css", "text/css"),
        "/static/vendor/plotly.min.js": ("vendor/plotly.min.js", "text/javascript"),
        **{f"/static/icons/{name}.svg": (f"icons/{name}.svg", "image/svg+xml")
           for name in ("arrow-right", "floppy-disk", "folder-open", "x")},
    }.items()}

    async def asset(request):
        data, mime = assets[request.path]
        return web.Response(body=data, content_type=mime)

    def review_for(request):
        sessions = request.query.getall("session", ())
        symbols = request.query.getall("symbol", ())
        if not sessions and not symbols and len(reviews) == 1:
            return next(iter(reviews.values()))
        if len(sessions) == 1 and not symbols and sessions[0] in reviews:
            return reviews[sessions[0]]
        if len(symbols) == 1 and not sessions and not same_market and symbols[0] in reviews:
            return reviews[symbols[0]]
        raise ReceiptError("Select one saved session for this blind review.")

    async def perform(request, operation, *selected):
        async def action():
            try:
                return await operation()
            except BlindReviewError as exc:
                raise ReceiptError(str(exc)) from exc
        kind = pair_kind if len(selected) == 2 else BLIND_REVIEW
        return await run_bounded(request, action, kind=kind, locks=tuple(locks[item] for item in selected))

    async def sources(_):
        return web.json_response({"symbols": [item.replay.symbol for item in reviews.values()]})

    async def sessions(_):
        return web.json_response({"sessions": [{"id": key, "symbol": item.replay.symbol}
                                               for key, item in reviews.items()]})

    async def status(request):
        review = review_for(request)
        return await perform(request, review.status, review)

    async def commit(request):
        review = review_for(request)
        body = await read_body(request)
        if set(body) != {"read"}:
            raise ReceiptError("Supply only the read to commit.")

        async def action():
            return {"commit": await review.commit_read(body["read"])}
        return await perform(request, action, review)

    async def reveal(request):
        review = review_for(request)
        if await read_body(request):
            raise ReceiptError("Reveal uses the committed read and its original cutoff.")

        async def action():
            return {"result": await review.reveal()}
        return await perform(request, action, review)

    async def save(request):
        review = review_for(request)
        body = await read_body(request)
        if set(body) != {"name"}:
            raise ReceiptError("Supply only the review receipt name.")
        name = validate_name(body["name"])

        async def action():
            if review.result is None:
                raise ReceiptError("Reveal the committed review before saving a receipt.")
            if review.receipt_id is not None:
                return store.load(review.receipt_id)
            receipt = store.save(assemble_receipt(name, BLIND_REVIEW, review.result))
            review.receipt_id = receipt["receipt_sha256"]
            return receipt
        return await perform(request, action, review)

    def receipt_metadata(matches, revealed):
        # User-entered names can describe an outcome. Show them only once
        # all the outcomes in this view have been revealed.
        fields = ("id", "kind", "created_at", "name") if revealed else ("id", "kind", "created_at")
        return web.json_response({"receipts": [{key: row[key] for key in fields}
                                               for row in store.list(matches=matches)]})

    async def receipts(request):
        review = review_for(request)
        if review.flip is None:
            return web.json_response({"receipts": []})
        checksum = review.flip["request"]["capture_sha256"]
        return receipt_metadata(lambda receipt: receipt["kind"] == BLIND_REVIEW
                                and receipt["request"].get("capture_sha256") == checksum,
                                review.result is not None)

    async def reopen(request):
        review = review_for(request)
        body = await read_body(request)
        receipt_id = body.get("id")
        if set(body) != {"id"} or not isinstance(receipt_id, str) or not ID_PATTERN.fullmatch(receipt_id):
            raise ReceiptError("Choose a saved review receipt to reopen.")

        async def action():
            receipt = store.load(receipt_id)
            if receipt["kind"] != BLIND_REVIEW:
                raise ReceiptError("Choose a saved blind review receipt.")
            verified = await reproduce_receipt(receipt, saved_replay=review.replay)
            if verified["status"] != "verified":
                raise ReceiptError("The saved review did not reproduce exactly.")
            review.restore(verified["result"], receipt_id)
            return {"result": review.result, "receipt_sha256": receipt_id, "name": receipt["name"]}
        return await perform(request, action, review)

    def export_saved(receipt_id, label):
        receipt = store.load(receipt_id)
        return web.Response(body=canonical_bytes(receipt), content_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="wind-tunnel-{label}-{receipt_id[:12]}.json"',
        })

    async def export(request):
        review = review_for(request)
        receipt_id = request.match_info["id"]
        if review.result is None or review.receipt_id != receipt_id:
            raise ReceiptError("Save or reopen this review before exporting its receipt.")
        return export_saved(receipt_id, "review")

    def require_pair(request):
        if len(paired) != 2 or request.query:
            raise ReceiptError("Open two distinct saved captures for a blind comparison.")

    def comparison_key():
        if all(item.result is not None for item in paired):
            # A committed ES request can have either the original ES-only proof or the current proof.
            return tuple(item.result["request_sha256"] for item in paired)
        return None

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
                raise ReceiptError("Commit and reveal both reviews before saving a comparison.")
            previous = comparison_receipts.get(key)
            if previous is not None:
                return store.load(previous)
            result = comparison.assemble_result(*(item.result for item in paired))
            receipt = store.save(assemble_receipt(name, pair_kind, result))
            comparison_receipts[key] = receipt["receipt_sha256"]
            return receipt
        return await perform(request, action, *paired)

    def comparison_slots(receipt):
        if same_market:
            return session_comparison.capture_slots(receipt["request"])
        selection = mixed_comparison.normalize_request(receipt["request"])
        return {(symbol, selection[symbol.lower()]["capture_sha256"]): symbol for symbol in pair_order}

    async def list_comparisons(request):
        require_pair(request)
        if any(item.replay.capture_sha256 is None for item in paired):
            return web.json_response({"receipts": []})
        captures = {(item.replay.symbol, item.replay.capture_sha256) for item in paired}

        def matches(receipt):
            if receipt["kind"] != pair_kind:
                return False
            try:
                return comparison_slots(receipt).keys() == captures
            except BlindReviewError:
                return False

        return receipt_metadata(matches, comparison_key() is not None)

    async def reopen_comparison(request):
        require_pair(request)
        body = await read_body(request)
        receipt_id = body.get("id")
        if set(body) != {"id"} or not isinstance(receipt_id, str) or not ID_PATTERN.fullmatch(receipt_id):
            raise ReceiptError("Choose a saved blind comparison receipt to reopen.")

        async def action():
            receipt = store.load(receipt_id)
            if receipt["kind"] != pair_kind:
                raise ReceiptError("Choose a saved blind comparison receipt.")
            binding = {key: key for key in reviews}
            if same_market:
                expected = comparison_slots(receipt)
                for key, item in reviews.items():
                    replay = item.replay
                    try:
                        checksum = replay.capture_sha256 or await asyncio.to_thread(saved_capture_digest, replay.path)
                    except (ValueError, OSError) as exc:
                        raise ReceiptError("A saved capture could not be read to reopen this comparison.") from exc
                    slot = expected.pop((replay.symbol, checksum), None)
                    if slot is None:
                        raise ReceiptError("Open both original saved captures to reopen this comparison.")
                    binding[key] = slot
            replays = {slot: reviews[key].replay for key, slot in binding.items()}
            if same_market:
                verified = await reproduce_receipt(receipt, session_replays=replays)
            else:
                verified = await reproduce_receipt(receipt, comparison_replays=replays)
            if verified["status"] != "verified":
                raise ReceiptError("The saved comparison did not reproduce exactly.")
            result = verified["result"]
            results_by_session = {key: result[slot.lower()] for key, slot in binding.items()}
            for key, item in reviews.items():
                side = results_by_session[key]
                if item.receipt_id is None or item.result["request_sha256"] != side["request_sha256"]:
                    item.restore(side, None)
            comparison_receipts[comparison_key()] = receipt_id
            return {"result": result, "results_by_session": results_by_session,
                    "receipt_sha256": receipt_id, "name": receipt["name"]}
        return await perform(request, action, *paired)

    async def export_comparison(request):
        require_pair(request)
        receipt_id = request.match_info["id"]
        if comparison_receipts.get(comparison_key()) != receipt_id:
            raise ReceiptError("Save or reopen this comparison before exporting its receipt.")
        return export_saved(receipt_id, "comparison")

    async def cleanup(_):
        store.close()
        for review in reviews.values():
            review.close()

    for route in assets:
        app.router.add_get(route, asset)
    app.router.add_get("/api/blind-review", status)
    app.router.add_get("/api/blind-review/sources", sources)
    app.router.add_get("/api/blind-review/sessions", sessions)
    app.router.add_post("/api/blind-review/commit", commit)
    app.router.add_post("/api/blind-review/reveal", reveal)
    app.router.add_post("/api/blind-review/save", save)
    app.router.add_get("/api/blind-review/receipts", receipts)
    app.router.add_post("/api/blind-review/reopen", reopen)
    app.router.add_get("/api/blind-review/receipts/{id}/export", export)
    app.router.add_get("/api/blind-review/comparison", comparison_status)
    app.router.add_post("/api/blind-review/comparison/save", save_comparison)
    app.router.add_get("/api/blind-review/comparison/receipts", list_comparisons)
    app.router.add_post("/api/blind-review/comparison/reopen", reopen_comparison)
    app.router.add_get("/api/blind-review/comparison/receipts/{id}/export", export_comparison)
    app.on_cleanup.append(cleanup)
    store = ReceiptStore(workspace)
    return app
