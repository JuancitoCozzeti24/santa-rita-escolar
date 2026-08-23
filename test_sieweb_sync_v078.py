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
    created=[x for x in merged["rows"] if isinstance(x,dict) and x.get("descripcion")=="Áreas y perímetros"][0]
    assert created["id"] is None
    assert created["idClaseContenido"] is None
    assert created["idpadre"] == 10
    assert created["nivelEva"] == 3
    assert created["campoInterno"] == "SE-CONSERVA"
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


def test_verified_save_sends_full_model_and_requires_editor_and_gradebook(monkeypatch):
    c=SieWebClient()
    raw=sample_raw()
    before={"criteria":[
        {"id":10,"idpadre":1,"nivelEva":2,"descripcion":"Modela objetos"},
        {"id":20,"idpadre":10,"nivelEva":3,"descripcion":"Desempeño anterior"},
    ],"class":{"idClase":123}}
    after=copy.deepcopy(before)
    after["criteria"].append({"id":21,"idpadre":10,"nivelEva":3,"descripcion":"Áreas y perímetros"})
    raw_after=sample_raw()
    raw_after["json"]["registros"].insert(2,{"id":21,"idClaseContenido":21,"idpadre":10,"nivelEva":3,
        "descripcion":"Áreas y perímetros","peso":100,"activo":True,"orden":2,"campoInterno":"SE-CONSERVA"})
    gradebook_calls=iter([before,after])
    criteria_calls=iter([raw,raw_after])
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: next(gradebook_calls))
    monkeypatch.setattr(c,"get_criteria",lambda **kwargs: next(criteria_calls))
    sent={}
    def fake_request(method,path,**kwargs):
        sent.update(kwargs["json"])
        return {"json":{"estado":1}}
    monkeypatch.setattr(c,"_request",fake_request)
    result=c.upsert_criteria_verified(
        class_id=123,class_period_id=6305,root_content_id=99,id_ambito=518,
        records=[{"descripcion":"Áreas y perímetros","idpadre":10,"nivelEva":3}],
        replica={},expected=[{"description":"Áreas y perímetros","parent_id":10,"level":3}],
        verification_attempts=1,
    )
    assert result["saved"] is True
    assert result["mode"] == "hierarchical-rescriterios-v0.7.10"
    assert len(sent["registros"]) == 4
    assert sent["datosReplica"] == []


def test_false_estado_1_is_rejected_if_gradebook_does_not_persist(monkeypatch):
    c=SieWebClient()
    raw=sample_raw()
    before={"criteria":[
        {"id":10,"idpadre":1,"nivelEva":2,"descripcion":"Modela objetos"},
        {"id":20,"idpadre":10,"nivelEva":3,"descripcion":"Desempeño anterior"},
    ],"class":{"idClase":123}}
    raw_after=sample_raw()
    raw_after["json"]["registros"].insert(2,{"id":21,"idClaseContenido":21,"idpadre":10,"nivelEva":3,
        "descripcion":"Áreas y perímetros","peso":100,"activo":True,"orden":2,"campoInterno":"SE-CONSERVA"})
    gradebook_calls=iter([before,before])
    criteria_calls=iter([raw,raw_after])
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: next(gradebook_calls))
    monkeypatch.setattr(c,"get_criteria",lambda **kwargs: next(criteria_calls))
    monkeypatch.setattr(c,"_request",lambda *a,**k:{"json":{"estado":1}})
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=123,class_period_id=6305,root_content_id=99,id_ambito=518,
            records=[{"descripcion":"Áreas y perímetros","idpadre":10,"nivelEva":3}],
            replica={},expected=[{"description":"Áreas y perímetros","parent_id":10,"level":3}],
            verification_attempts=1,
        )
    assert "FALSO ÉXITO SIEWEB" in str(exc.value)


def test_e0006_or_non_success_is_rejected_before_any_grade_flow(monkeypatch):
    c=SieWebClient()
    raw=sample_raw()
    before={"criteria":[
        {"id":10,"idpadre":1,"nivelEva":2,"descripcion":"Modela objetos"},
        {"id":20,"idpadre":10,"nivelEva":3,"descripcion":"Desempeño anterior"},
    ],"class":{"idClase":123}}
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: before)
    monkeypatch.setattr(c,"get_criteria",lambda **kwargs: raw)
    monkeypatch.setattr(c,"_request",lambda *a,**k:{"json":{"estado":0,"codigo":"e0006"}})
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=123,class_period_id=6305,root_content_id=99,id_ambito=518,
            records=[{"descripcion":"Áreas y perímetros","idpadre":10,"nivelEva":3}],
            replica={},expected=[{"description":"Áreas y perímetros","parent_id":10,"level":3}],
            verification_attempts=1,
        )
    assert "e0006" in str(exc.value)
