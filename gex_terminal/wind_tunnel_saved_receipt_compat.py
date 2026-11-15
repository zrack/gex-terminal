"""Reproduce earlier ES receipts on the shared ES/NQ calculations."""

from .wind_tunnel import _sha


_ES_ONLY_IMPLEMENTATION = {
    "wind_tunnel_saved_replay.py": "3e6fd2680c351761b1a2abddc87efda83eb08d7381f0a9aa0f374df3aae70435",
    "wind_tunnel_saved_investigation.py": "7f8e0fd0b0a0d035b0c4be1b67bc7a7418ebab0fea715ab8b312287b949e23b3",
}
_ES_ONLY_IMPLEMENTATIONS = {
    "investigate-saved": (_ES_ONLY_IMPLEMENTATION,),
    "blind-review": ({
        "wind_tunnel_blind_review.py": "96f68c2b07d7acf24d5f165d77bb175a4dfca486084ad118dcc5812b20e132f2",
        "wind_tunnel_blind_replay.py": "848a3951d7213067038209d25e3b72976fe7c7a848bf60dcf3fc5580619278bc",
    },),
    "blind-study": (
        {"wind_tunnel_blind_study.py": "69fa343e78c818517ac46529c4ee22cc963ebdaeae510d74f2bcc61acb6f3386"},
        {"wind_tunnel_blind_study.py": "803be0b69d95b4eb868ddda5eceb02919a5300b2c10aae700c98a577ba501a2f"},
    ),
    "blind-saved-study": ({
        "wind_tunnel_blind_study.py": "803be0b69d95b4eb868ddda5eceb02919a5300b2c10aae700c98a577ba501a2f",
        "wind_tunnel_blind_saved_study.py": "22adf6caeb4a7281b7281f6e40c2fb9051c71fc79a399f5b6c525b49c182a00a",
    },),
}


def matches_es_only_build(kind: str, recorded: dict, current: dict) -> bool:
    # Only the pinned modules can differ. Runtime and all other owning
    # source identities must still match the current build exactly.
    return any(recorded == {**current, "implementation": {**current["implementation"], **original}}
               for original in _ES_ONLY_IMPLEMENTATIONS.get(kind, ()))


def with_recorded_identity(result: dict, recorded: dict) -> dict:
    # The computed output still has to match the receipt byte for byte. Use
    # the result producer's digest encoding for the legacy envelope.
    original_format = {**result, "calculation": recorded, "calculation_fingerprint": _sha(recorded)}
    original_format.pop("result_sha256")
    original_format["result_sha256"] = _sha(original_format)
    return original_format
