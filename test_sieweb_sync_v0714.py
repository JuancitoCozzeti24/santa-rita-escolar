import copy

import pytest

from sieweb import SieWebClient, SieWebError
from test_sieweb_sync_v0710 import gradebook, real_shape_raw


NATIVE_RECORD_KEYS = {
    "ID_CLASE_CONTENIDO", "ID_CLASE", "ID_CLASE_PERIODO", "EXCLUIR", "SUMATIVO",
    "PESO", "ID_CONTENIDO", "DESCRIPCION", "ID_PROGRAMA", "ID_CONTENIDO_REF",
    "ABREVIATURA", "INCLUSIVO", "ORDEN", "BASE", "INDICE", "replicar",
    "TRADUCCION", "NIVEL_PADRE", "LLAVE", "COLORP", "DESCP", "ICONOP",
}


def official_raw(include_new=False):
    raw=real_shape_raw(include_new)
    raw["json"]["dataPrograma"]={
        "objProgramas":{
            "4":[{
                "ID_PROGRAMA":5,"ID_PROGRAMA_REF":4,"DESCRIPCION":"Desempeño",
                "ICONO":"simbolo5","COLOR":"#ffffff","NIVEL":4,"LIMITE":6,
            }]
        },
        "objLimites":{"5":6},
    }
    return raw


def install_live_shape_mocks(monkeypatch, client, *, raw_after=None, grade_after=None,
                             provider=None):
    raws=iter([official_raw(False), raw_after or official_raw(True)])
    summaries=iter([gradebook(False), grade_after or gradebook(True)])

    def get_criteria(**kwargs):
        client._last_criteria_context={
            "idClase":2030,"idClasePeriodo":6305,"idContenido":119598,
            "idAmbito":518,"CURSOCOD":"05","cursocod":"05",
        }
        return next(raws)

    sent=[]
    monkeypatch.setattr(client,"get_criteria",get_criteria)
    monkeypatch.setattr(client,"get_gradebook_summary",lambda **kwargs: next(summaries))
    monkeypatch.setattr(
        client,"_request",
        lambda method,path,**kwargs: sent.append(copy.deepcopy(kwargs["json"]))
        or (provider or {"json":{"estado":1}}),
    )
    return sent


def test_v0714_matches_official_default_data_contenido_contract(monkeypatch):
    c=SieWebClient()
    sent=install_live_shape_mocks(monkeypatch,c)
    result=c.upsert_criteria_verified(
        class_id=2030,class_period_id=6305,root_content_id=119598,id_ambito=518,
        records=[{"descripcion":"AREAS PERIM.","idpadre":133731,"nivelEva":3,
                  "ABREVIATURA":"AREAS PERIM."}],
        replica=[],
        expected=[{"description":"AREAS PERIM.","parent_id":133731,"level":3}],
        verification_attempts=1,
    )
    assert result["saved"] is True
    assert result["write_strategy"] == "ui-native-modal-new-record"
    assert len(sent) == 1
    payload=sent[0]
    assert set(payload) == {"registros","idClase","datosReplica"}
    assert payload["idClase"] == 2030
    assert payload["datosReplica"] == {
        "periodo":2,"idCurso":24,"grupocod":"001","cursocod":"05",
        "limiteReplica":1,"replicar":False,
    }
    assert len(payload["registros"]) == 1
    record=payload["registros"][0]
    assert set(record) == NATIVE_RECORD_KEYS
    assert record == {
        "ID_CLASE_CONTENIDO":0,"ID_CLASE":2030,"ID_CLASE_PERIODO":6305,
        "EXCLUIR":0,"SUMATIVO":0,"PESO":1,"ID_CONTENIDO":0,
        "DESCRIPCION":"AREAS PERIM.","ID_PROGRAMA":5,
        "ID_CONTENIDO_REF":133731,"ABREVIATURA":"AREAS PERIM.","INCLUSIVO":0,
        "ORDEN":1,"BASE":0,"INDICE":2,"replicar":False,"TRADUCCION":None,
        "NIVEL_PADRE":2,"LLAVE":"5-2_4-1_3-3_2-1","COLORP":"#ffffff",
        "DESCP":"Desempeño","ICONOP":"simbolo5",
    }


def test_v0714_false_estado_one_never_unlocks_grade_write(monkeypatch):
    c=SieWebClient()
    sent=install_live_shape_mocks(
        monkeypatch,c,raw_after=official_raw(False),grade_after=gradebook(False)
    )
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=2030,class_period_id=6305,root_content_id=119598,id_ambito=518,
            records=[{"descripcion":"AREAS PERIM.","idpadre":133731,"nivelEva":3}],
            replica=[],expected=[{"description":"AREAS PERIM.","parent_id":133731,"level":3}],
            verification_attempts=1,
        )
    assert "FALSO ÉXITO SIEWEB" in str(exc.value)
    assert "NO se escribirán calificaciones" in str(exc.value)
    assert len(sent) == 1


def test_v0714_existing_performance_is_idempotent_and_sends_no_post(monkeypatch):
    c=SieWebClient()
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: gradebook(True))

    def get_criteria(**kwargs):
        c._last_criteria_context={
            "idClase":2030,"idClasePeriodo":6305,"idContenido":119598,
            "idAmbito":518,"CURSOCOD":"05","cursocod":"05",
        }
        return official_raw(True)

    monkeypatch.setattr(c,"get_criteria",get_criteria)
    monkeypatch.setattr(c,"_request",lambda *args,**kwargs: pytest.fail("no debe hacer POST"))
    result=c.upsert_criteria_verified(
        class_id=2030,class_period_id=6305,root_content_id=119598,id_ambito=518,
        records=[{"descripcion":"AREAS PERIM.","idpadre":133731,"nivelEva":3}],
        replica=[],expected=[{"description":"AREAS PERIM.","parent_id":133731,"level":3}],
        verification_attempts=1,
    )
    assert result["already_present"] is True
    assert result["sent_record_count"] == 0
    assert result["write_strategy"] == "no-post-already-present"


def test_v0714_blocks_replica_context_mismatch_before_post(monkeypatch):
    c=SieWebClient()
    monkeypatch.setattr(c,"get_gradebook_summary",lambda **kwargs: gradebook(False))

    def get_criteria(**kwargs):
        c._last_criteria_context={
            "idClase":2030,"idClasePeriodo":6305,"idContenido":119598,
            "idAmbito":518,"CURSOCOD":"05","cursocod":"05",
        }
        return official_raw(False)

    monkeypatch.setattr(c,"get_criteria",get_criteria)
    monkeypatch.setattr(c,"_request",lambda *args,**kwargs: pytest.fail("no debe hacer POST"))
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=2030,class_period_id=6305,root_content_id=119598,id_ambito=518,
            records=[{"descripcion":"AREAS PERIM.","idpadre":133731,"nivelEva":3}],
            replica={"cursocod":"99"},
            expected=[{"description":"AREAS PERIM.","parent_id":133731,"level":3}],
            verification_attempts=1,
        )
    assert "no coincide con el contexto leído" in str(exc.value)


def test_v084_selects_program_five_even_when_it_is_not_the_first_choice():
    c = SieWebClient()
    raw = official_raw(False)
    raw["json"]["dataPrograma"]["objProgramas"]["4"] = [
        {
            "ID_PROGRAMA": 6, "ID_PROGRAMA_REF": 4,
            "DESCRIPCION": "Evidencia", "ICONO": "simbolo6",
            "COLOR": "#eeeeee", "LIMITE": 4,
        },
        {
            "ID_PROGRAMA": 5, "ID_PROGRAMA_REF": 4,
            "DESCRIPCION": "Desempeño", "ICONO": "simbolo5",
            "COLOR": "#ffffff", "LIMITE": 6,
        },
    ]
    parent = c._find_tree_nodes(
        raw["json"]["resCriterios"], content_id=133731, level=2
    )[0][1]
    program = c._native_child_program(raw, parent)
    assert program["ID_PROGRAMA"] == 5


def test_v084_blocks_multi_insert_when_native_replica_contexts_disagree(monkeypatch):
    c = SieWebClient()
    raw = official_raw(False)
    second_parent = copy.deepcopy(raw["json"]["resCriterios"][0]["children"][0])
    second_parent.update({
        "ID_CLASE_CONTENIDO": 233463,
        "ID_CONTENIDO": 233731,
        "DESCRIPCION": "Comunica su comprensión",
        "GRUPOCOD": "002",
        "LLAVE": "4-2_3-3_2-1",
        "INDICE": 2,
        "children": [],
    })
    raw["json"]["resCriterios"][0]["children"].append(second_parent)
    summary = gradebook(False)
    summary["criteria"].append({
        "id": 233731, "idpadre": 125378, "nivelEva": 2,
        "descripcion": "Comunica su comprensión",
    })
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: summary)

    def get_criteria(**kwargs):
        c._last_criteria_context = {
            "idClase": 2030, "idClasePeriodo": 6305, "idContenido": 119598,
            "idAmbito": 518, "CURSOCOD": "05", "cursocod": "05",
        }
        return raw

    monkeypatch.setattr(c, "get_criteria", get_criteria)
    monkeypatch.setattr(c, "_request", lambda *args, **kwargs: pytest.fail("no debe hacer POST"))
    with pytest.raises(SieWebError, match="no comparten el mismo paramDatosReplica"):
        c.upsert_criteria_verified(
            class_id=2030, class_period_id=6305, root_content_id=119598, id_ambito=518,
            records=[
                {"descripcion": "Desempeño A", "idpadre": 133731, "nivelEva": 3},
                {"descripcion": "Desempeño B", "idpadre": 233731, "nivelEva": 3},
            ],
            replica={},
            expected=[
                {"description": "Desempeño A", "parent_id": 133731, "level": 3},
                {"description": "Desempeño B", "parent_id": 233731, "level": 3},
            ],
            verification_attempts=1,
        )
