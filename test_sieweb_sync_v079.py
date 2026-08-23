import copy
import pytest
from sieweb import SieWebClient, SieWebError


def raw_for_class(class_id=222, class_period_id=7002):
    return {
        "json": {
            "datosReplica": [],
            "registros": [
                {"id": 100, "idClaseContenido": 100, "idClase": class_id,
                 "idClasePeriodo": class_period_id, "idpadre": 1, "nivelEva": 2,
                 "descripcion": "Modela objetos", "peso": 25},
                {"id": 101, "idClaseContenido": 101, "idClase": class_id,
                 "idClasePeriodo": class_period_id, "idpadre": 100, "nivelEva": 3,
                 "descripcion": "Anterior", "peso": 100},
            ]
        }
    }


def summary_for_class(class_id=222, class_period_id=7002, root=9002, include_new=False):
    criteria=[
        {"id":100,"idpadre":1,"nivelEva":2,"descripcion":"Modela objetos"},
        {"id":101,"idpadre":100,"nivelEva":3,"descripcion":"Anterior"},
    ]
    if include_new:
        criteria.append({"id":102,"idpadre":100,"nivelEva":3,"descripcion":"Áreas y perímetros"})
    return {
        "class":{"idClase":class_id,"idClasePeriodo":class_period_id,"idContenidoPrin":root},
        "criteria":criteria,
    }


def test_v079_passes_exact_ambito_to_pre_and_post_verification_reads(monkeypatch):
    c=SieWebClient()
    seen=[]
    raw_before=raw_for_class()
    raw_after=copy.deepcopy(raw_before)
    raw_after["json"]["registros"].append({
        "id":102,"idClaseContenido":102,"idClase":222,"idClasePeriodo":7002,
        "idpadre":100,"nivelEva":3,"descripcion":"Áreas y perímetros","peso":100,
    })
    raw_iter=iter([raw_before,raw_after])
    summaries=iter([summary_for_class(),summary_for_class(include_new=True)])
    def fake_get_criteria(**kwargs):
        seen.append(kwargs.get("id_ambito"))
        return next(raw_iter)
    monkeypatch.setattr(c,"get_criteria",fake_get_criteria)
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: next(summaries))
    monkeypatch.setattr(c,"_request",lambda *a,**k:{"json":{"estado":1}})
    result=c.upsert_criteria_verified(
        class_id=222,class_period_id=7002,root_content_id=9002,id_ambito=619,
        records=[{"descripcion":"Áreas y perímetros","idpadre":100,"nivelEva":3}],
        replica={},expected=[{"description":"Áreas y perímetros","parent_id":100,"level":3}],
        verification_attempts=1,
    )
    assert seen == [619,619]
    assert result["idAmbito"] == 619
    assert result["context_guard"] == "exact-ambito-bound-tree-v0.7.10"


def test_v079_blocks_editor_rows_from_another_section_before_post(monkeypatch):
    c=SieWebClient()
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: summary_for_class(class_id=222))
    monkeypatch.setattr(c,"get_criteria",lambda **kwargs: raw_for_class(class_id=333))
    called={"post":False}
    def bad_post(*a,**k):
        called["post"]=True
        return {"json":{"estado":1}}
    monkeypatch.setattr(c,"_request",bad_post)
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=222,class_period_id=7002,root_content_id=9002,id_ambito=619,
            records=[{"descripcion":"Áreas y perímetros","idpadre":100,"nivelEva":3}],
            replica={},expected=[{"description":"Áreas y perímetros","parent_id":100,"level":3}],
            verification_attempts=1,
        )
    assert "PROTECCIÓN DE CONTEXTO SIEWEB" in str(exc.value)
    assert called["post"] is False


def test_v079_requires_ambito_instead_of_silent_default(monkeypatch):
    c=SieWebClient()
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=222,class_period_id=7002,root_content_id=9002,id_ambito=0,
            records=[{"descripcion":"Áreas y perímetros","idpadre":100,"nivelEva":3}],
            replica={},expected=[{"description":"Áreas y perímetros","parent_id":100,"level":3}],
            verification_attempts=1,
        )
    assert "id_ambito" in str(exc.value)


def test_v079_gradebook_context_mismatch_blocks_write(monkeypatch):
    c=SieWebClient()
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: summary_for_class(class_id=999))
    called={"criteria":False,"post":False}
    monkeypatch.setattr(c,"get_criteria",lambda **kwargs: called.__setitem__("criteria",True))
    monkeypatch.setattr(c,"_request",lambda *a,**k: called.__setitem__("post",True))
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=222,class_period_id=7002,root_content_id=9002,id_ambito=619,
            records=[{"descripcion":"Áreas y perímetros","idpadre":100,"nivelEva":3}],
            replica={},expected=[{"description":"Áreas y perímetros","parent_id":100,"level":3}],
            verification_attempts=1,
        )
    assert "PROTECCIÓN DE CONTEXTO SIEWEB" in str(exc.value)
    assert called["criteria"] is False
    assert called["post"] is False
