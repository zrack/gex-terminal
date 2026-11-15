"""Reproduce earlier ES receipts on the shared ES/NQ calculations."""

from .wind_tunnel import _sha


_ES_ONLY_IMPLEMENTATION = {
    "wind_tunnel_saved_replay.py": "3e6fd2680c351761b1a2abddc87efda83eb08d7381f0a9aa0f374df3aae70435",
    "wind_tunnel_saved_investigation.py": "7f8e0fd0b0a0d035b0c4be1b67bc7a7418ebab0fea715ab8b312287b949e23b3",
}
_ES_ONLY_IMPLEMENTATIONS = {
    "investigate-saved": _ES_ONLY_IMPLEMENTATION,
    "blind-review": {
        "wind_tunnel_blind_review.py": "96f68c2b07d7acf24d5f165d77bb175a4dfca486084ad118dcc5812b20e132f2",
        "wind_tunnel_blind_replay.py": "848a3951d7213067038209d25e3b72976fe7c7a848bf60dcf3fc5580619278bc",
    },
}


def matches_es_only_build(kind: str, recorded: dict, current: dict) -> bool:
    # Only the two generalized modules differ. Runtime and all other owning
    # source identities must still match the current build exactly.
    original = _ES_ONLY_IMPLEMENTATIONS.get(kind)
    return original is not None and recorded == {
        **current, "implementation": {**current["implementation"], **original},
    }


def with_recorded_identity(result: dict, recorded: dict) -> dict:
    # The computed output still has to match the receipt byte for byte. Use
    # the result producer's digest encoding for the legacy envelope.
    original_format = {**result, "calculation": recorded, "calculation_fingerprint": _sha(recorded)}
    original_format.pop("result_sha256")
    original_format["result_sha256"] = _sha(original_format)
    return original_format
