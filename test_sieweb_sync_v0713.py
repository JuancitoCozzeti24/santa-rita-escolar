import copy

import pytest

from sieweb import SieWebClient, SieWebError
from test_sieweb_sync_v0710 import gradebook, real_shape_raw


def test_v0713_get_sends_lowercase_binding_required_by_provider(monkeypatch):
    """Reproduce el HTTP 500 real si falta el binding minúsculo."""
    c = SieWebClient()
    monkeypatch.setattr(
        c,
        "list_classes",
        lambda **kwargs: {"json": [{"ID_CLASE": 2030, "CURSOCOD": "05"}]},
    )

    def provider_contract(method, path, **kwargs):
        params = copy.deepcopy(kwargs["params"])
        if not params.get("cursocod"):
            raise AssertionError("Undefined binding CG.CURSOCOD: falta cursocod")
        assert params["CURSOCOD"] == params["cursocod"] == "05"
        return {"json": {"resCriterios": []}}

    monkeypatch.setattr(c, "_request", provider_contract)
    result = c.get_criteria(
        class_id=2030,
        class_period_id=6305,
        root_content_id=119598,
        id_ambito=518,
    )
    assert result["json"]["resCriterios"] == []


def test_v0713_post_is_blocked_if_editor_context_is_stale(monkeypatch):
    c = SieWebClient()
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: gradebook(False))

    def stale_editor(**kwargs):
        c._last_criteria_context = {
            "idClase": 2043,
            "idClasePeriodo": 6318,
            "idContenido": 119598,
            "idAmbito": 519,
            "CURSOCOD": "05",
            "cursocod": "05",
        }
        return real_shape_raw(False)

    monkeypatch.setattr(c, "get_criteria", stale_editor)
    posted = {"value": False}

    def forbidden_post(*args, **kwargs):
        posted["value"] = True
        return {"json": {"estado": 1}}

    monkeypatch.setattr(c, "_request", forbidden_post)
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=2030,
            class_period_id=6305,
            root_content_id=119598,
            id_ambito=518,
            records=[{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3}],
            replica=[],
            expected=[{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
            verification_attempts=1,
        )
    assert "contexto exacto requerido" in str(exc.value)
    assert posted["value"] is False
