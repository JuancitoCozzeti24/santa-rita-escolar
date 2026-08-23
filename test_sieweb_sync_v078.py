import copy
import pytest
from sieweb import SieWebClient, SieWebError


def sample_raw():
    return {
        "json": {
            "otraLista": [{"foo": 1}, {"bar": 2}],
            "datosReplica": [{"idClase": 123, "activo": True}],
            "registros": [
                {"id": 10, "idClaseContenido": 10, "idpadre": 1, "nivelEva": 2,
                 "descripcion": "Modela objetos", "peso": 25, "activo": True, "orden": 1},
                {"id": 20, "idClaseContenido": 20, "idpadre": 10, "nivelEva": 3,
                 "descripcion": "Desempeño anterior", "peso": 100, "activo": True, "orden": 1,
                 "campoInterno": "SE-CONSERVA"},
                {"id": 30, "idClaseContenido": 30, "idpadre": 2, "nivelEva": 2,
                 "descripcion": "Argumenta", "peso": 25, "activo": True, "orden": 2},
            ],
        }
    }


def test_extracts_full_editor_collection_not_arbitrary_nested_dict():
    c=SieWebClient()
    model=c.extract_criteria_editor_model(sample_raw())
    assert model["path"][-1] == "registros"
    assert len(model["rows"]) == 3


def test_new_performance_is_inserted_into_full_model_and_preserves_sibling_schema():
    c=SieWebClient()
    model=c.extract_criteria_editor_model(sample_raw())
    requested={"descripcion":"Áreas y perímetros","idpadre":10,"nivelEva":3}
    merged=c.merge_requested_criteria_into_editor_rows(
        model["rows"], [requested],
        [{"description":"Áreas y perímetros","parent_id":10,"level":3}],
    )
    assert len(merged["rows"]) == 4
    created=[x for x in merged["rows"] if isinstance(x,dict)
             and c._raw_row_matches(x,description="Áreas y perímetros",parent_id=10,level=3)][0]
    assert created["ID_CONTENIDO"] is None
    assert created["ID_CLASE_CONTENIDO"] is None
    assert created["ID_CONTENIDO_REF"] == 10
    assert c._criterion_level(created) == 3
    assert created["flExiste"] is False and created["EDITOREG"] == 1
    assert "campoInterno" not in created and "activo" not in created
    # Las demás filas originales permanecen intactas.
    assert merged["rows"][0] == model["rows"][0]


def test_edit_updates_real_row_inside_full_model_without_destroying_identity():
    c=SieWebClient()
    rows=c.extract_criteria_editor_model(sample_raw())["rows"]
    requested={"descripcion":"Desempeño anterior","idpadre":10,"nivelEva":3,"peso":75}
    merged=c.merge_requested_criteria_into_editor_rows(
        rows,[requested],[{"description":"Desempeño anterior","parent_id":10,"level":3}],
    )
    row=[x for x in merged["rows"] if isinstance(x,dict) and x.get("id")==20][0]
    assert row["idClaseContenido"] == 20
    assert row["peso"] == 75
    assert row["campoInterno"] == "SE-CONSERVA"


def test_legacy_flat_editor_is_readable_but_blocked_for_native_modal_write(monkeypatch):
    c=SieWebClient()
    raw=sample_raw()
    before={"criteria":[
        {"id":10,"idpadre":1,"nivelEva":2,"descripcion":"Modela objetos"},
        {"id":20,"idpadre":10,"nivelEva":3,"descripcion":"Desempeño anterior"},
    ],"class":{"idClase":123}}
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: before)
    def fake_get_criteria(**kwargs):
        c._last_criteria_context = {
            "idClase": 123, "idClasePeriodo": 6305, "idContenido": 99,
            "idAmbito": 518, "CURSOCOD": "05", "cursocod": "05",
        }
        return raw
    monkeypatch.setattr(c,"get_criteria",fake_get_criteria)
    sent=[]
    def fake_request(method,path,**kwargs):
        sent.append(kwargs["json"])
        return {"json":{"estado":1}}
    monkeypatch.setattr(c,"_request",fake_request)
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=123,class_period_id=6305,root_content_id=99,id_ambito=518,
            records=[{"descripcion":"Áreas y perímetros","idpadre":10,"nivelEva":3}],
            replica={},expected=[{"description":"Áreas y perímetros","parent_id":10,"level":3}],
            verification_attempts=1,
        )
    assert "capacidad padre" in str(exc.value)
    assert sent == []
