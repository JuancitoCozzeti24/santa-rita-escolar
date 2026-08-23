import copy
import pytest

from sieweb import SieWebClient, SieWebError


def real_shape_raw(include_new=False):
    perf = {
        "ID_CLASE_CONTENIDO": 133495,
        "ID_CLASE": 2030,
        "ID_CONTENIDO": 133763,
        "PESO": 1,
        "ORDEN": 1,
        "INCLUSIVO": 0,
        "SUMATIVO": 0,
        "EXCLUIR_PORCENTAJE": 0,
        "EXCLUIR": 0,
        "ORDEN_PROG": None,
        "ID_PROGRAMA": 5,
        "ID_CONTENIDO_REF": 133731,
        "DESCRIPCION": "Teoremas de triángulos",
        "INDICE": 1,
        "ABREVIATURA": "TEOREMAS TRIÁNGULO",
        "ID_CURSO": 24,
        "GRUPOCOD": "001",
        "COLOR": "#ffffff",
        "ID_CLASE_PERIODO": 6305,
        "DESCPROGRAMA": "Desempeño",
        "TRADUCCION": None,
        "ICONO": "simbolo5",
        "NIVEL": 3,
        "TIPO_EVA": 1,
        "FL_CONCLUSION": 1,
        "LLAVE": "5-1_4-1_3-3_2-1",
        "PESO_ORIGI": 1,
        "ORIGI": "Teoremas de triángulos",
        "ABREV_ORIGI": "TEOREMAS TRIÁNGULO",
        "TRAD_ORIGI": None,
        "EDITOREG": 0,
        "INDICE_ORIGI": 1,
        "flExiste": True,
        "bloquearCriterio": False,
        "children": [],
    }
    children = [perf]
    if include_new:
        new = copy.deepcopy(perf)
        new.update({
            "ID_CLASE_CONTENIDO": 140001,
            "ID_CONTENIDO": 140101,
            "DESCRIPCION": "AREAS PERIM.",
            "ABREVIATURA": "AREAS PERIM.",
            "INDICE": 2,
            "INDICE_ORIGI": 2,
            "ORDEN": 2,
            "LLAVE": "5-2_4-1_3-3_2-1",
            "ORIGI": "AREAS PERIM.",
            "ABREV_ORIGI": "AREAS PERIM.",
            "flExiste": True,
        })
        children.append(new)
    modela = {
        "ID_CLASE_CONTENIDO": 133463,
        "ID_CLASE": 2030,
        "ID_CONTENIDO": 133731,
        "PESO": 1,
        "ORDEN": 1,
        "INCLUSIVO": 0,
        "SUMATIVO": 0,
        "EXCLUIR_PORCENTAJE": 0,
        "EXCLUIR": 0,
        "ORDEN_PROG": None,
        "ID_PROGRAMA": 4,
        "ID_CONTENIDO_REF": 125378,
        "DESCRIPCION": "Modela objetos ",
        "INDICE": 1,
        "ABREVIATURA": None,
        "ID_CURSO": 24,
        "GRUPOCOD": "001",
        "COLOR": "#ffff88",
        "ID_CLASE_PERIODO": 6305,
        "DESCPROGRAMA": "Capacidad",
        "TRADUCCION": None,
        "ICONO": "simbolo10",
        "NIVEL": 2,
        "TIPO_EVA": 1,
        "FL_CONCLUSION": 1,
        "LLAVE": "4-1_3-3_2-1",
        "PESO_ORIGI": 1,
        "ORIGI": "Modela objetos ",
        "ABREV_ORIGI": None,
        "TRAD_ORIGI": None,
        "EDITOREG": 0,
        "INDICE_ORIGI": 1,
        "flExiste": True,
        "bloquearCriterio": False,
        "children": children,
    }
    comp = {
        "ID_CLASE_CONTENIDO": 125110,
        "ID_CLASE": 2030,
        "ID_CONTENIDO": 125378,
        "PESO": 1,
        "ORDEN": 3,
        "ID_PROGRAMA": 3,
        "ID_CONTENIDO_REF": 119598,
        "DESCRIPCION": "Resuelve problemas de movimiento, forma y localización",
        "INDICE": 3,
        "ABREVIATURA": None,
        "ID_CURSO": 24,
        "GRUPOCOD": "001",
        "COLOR": "#c7d7ed",
        "ID_CLASE_PERIODO": 6305,
        "DESCPROGRAMA": "Competencia",
        "NIVEL": 1,
        "TIPO_EVA": 1,
        "LLAVE": "3-3_2-1",
        "PESO_ORIGI": 1,
        "ORIGI": "Resuelve problemas de movimiento, forma y localización",
        "EDITOREG": 0,
        "INDICE_ORIGI": 3,
        "flExiste": True,
        "bloquearCriterio": False,
        "children": [modela],
    }
    # Las plazas vacías reales están en raíz y NO deben confundirse con hijos nuevos.
    blank = {
        "ABREVIATURA": None, "ABREV_ORIGI": None, "COLOR": "#c7d7ed",
        "DESCPROGRAMA": "Competencia", "DESCRIPCION": "", "EDITOREG": 0,
        "EXCLUIR": 0, "ICONO": "simbolo13", "ID_CLASE_CONTENIDO": None,
        "ID_CONTENIDO": None, "ID_CONTENIDO_REF": 119598, "ID_PROGRAMA": 3,
        "INCLUSIVO": 0, "INDICE": 4, "INDICE_ORIGI": 4, "ORDEN": 4,
        "ORIGI": "", "PESO": "", "PESO_ORIGI": "", "SUMATIVO": 0,
        "EXCLUIR_PORCENTAJE": 0, "TRADUCCION": None, "TRAD_ORIGI": None,
        "LLAVE": "3-4_2-1", "flExiste": False, "bloquearCriterio": False,
        "children": [],
    }
    return {"json": {
        "resCriterios": [comp, blank],
        "resBancoDatos": [],
        "nivelReplicaAnual": [{"LIMITE": 1}],
        "objOrigenReplica": {"esOrigen": False, "existeClaseOrigen": False,
                              "ngsOrigen": "", "clasesNG": [2030, 2043]},
        "longitudCriterios": 800,
    }}


def gradebook(include_new=False):
    criteria = [
        {"id": 125378, "idpadre": 119598, "nivelEva": 1,
         "descripcion": "Resuelve problemas de movimiento, forma y localización"},
        {"id": 133731, "idpadre": 125378, "nivelEva": 2,
         "descripcion": "Modela objetos"},
        {"id": 133763, "idpadre": 133731, "nivelEva": 3,
         "descripcion": "Teoremas de triángulos"},
    ]
    if include_new:
        criteria.append({"id": 140101, "idpadre": 133731, "nivelEva": 3,
                         "descripcion": "AREAS PERIM."})
    return {
        "class": {"idClase": 2030, "idClasePeriodo": 6305,
                  "idContenidoPrin": 119598, "nomSalon": "S2A"},
        "criteria": criteria,
    }


def test_real_fields_parent_and_level_are_recognized():
    c = SieWebClient()
    raw = real_shape_raw()
    model = c.extract_criteria_editor_model(raw)
    assert model["path"] == ["json", "resCriterios"]
    assert model["tree"] is True
    nodes = c._find_tree_nodes(model["rows"], description="Modela objetos", level=2)
    assert len(nodes) == 1
    row = nodes[0][1]
    assert c._criterion_parent(row) == 125378
    assert c._criterion_level(row) == 2
    assert c._criterion_content_id(row) == 133731


def test_new_performance_is_child_of_modela_not_root_and_uses_unsaved_markers():
    c = SieWebClient()
    model = c.extract_criteria_editor_model(real_shape_raw())
    original_root_count = len(model["rows"])
    merged = c.merge_requested_criteria_into_editor_rows(
        model["rows"],
        [{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3,
          "ABREVIATURA": "AREAS PERIM."}],
        [{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
    )
    assert len(merged["rows"]) == original_root_count
    found = c._find_tree_nodes(merged["rows"], description="AREAS PERIM.",
                               parent_id=133731, level=3)
    assert len(found) == 1
    path, row = found[0]
    assert path[:3] == (0, "children", 0)
    assert row["ID_CLASE_CONTENIDO"] is None
    assert row["ID_CONTENIDO"] is None
    assert row["ID_CONTENIDO_REF"] == 133731
    assert "NIVEL" not in row
    assert c._criterion_level(row) == 3
    for forbidden in ("ID_CLASE","ID_CURSO","GRUPOCOD","ID_CLASE_PERIODO","TIPO_EVA","FL_CONCLUSION","ORDEN_PROG"):
        assert forbidden not in row
    assert row["INDICE"] == 2 and row["INDICE_ORIGI"] == 2 and row["ORDEN"] == 2
    assert row["LLAVE"] == "5-2_4-1_3-3_2-1"
    assert row["flExiste"] is False
    assert row["EDITOREG"] == 1
    assert row["ORIGI"] == ""
    assert row["PESO_ORIGI"] == ""
    assert row["ABREV_ORIGI"] is None
    assert row["ABREVIATURA"] == "AREAS PERIM."


def test_edit_marks_editoreg_instead_of_silent_noop():
    c = SieWebClient()
    model = c.extract_criteria_editor_model(real_shape_raw())
    merged = c.merge_requested_criteria_into_editor_rows(
        model["rows"],
        [{"DESCRIPCION": "Teoremas de triángulos", "ABREVIATURA": "TRIANG."}],
        [{"description": "Teoremas de triángulos", "parent_id": 133731, "level": 3}],
    )
    row = c._find_tree_nodes(merged["rows"], description="Teoremas de triángulos",
                             parent_id=133731, level=3)[0][1]
    assert row["ID_CONTENIDO"] == 133763
    assert row["ID_CLASE_CONTENIDO"] == 133495
    assert row["LLAVE"] == "5-1_4-1_3-3_2-1"
    assert row["EDITOREG"] == 1
    assert row["flExiste"] is True
    assert row["ABREVIATURA"] == "TRIANG."


def test_empty_replica_is_omitted_instead_of_invented():
    c = SieWebClient()
    assert c.normalize_replica_for_criteria_write({}) is None
    assert c.normalize_replica_for_criteria_write(None) is None
    with pytest.raises(SieWebError):
        c.normalize_replica_for_criteria_write({"clasesNG": [2043]})


def test_verified_write_payload_matches_hierarchy_and_double_verifies(monkeypatch):
    c = SieWebClient()
    raw_before = real_shape_raw(False)
    raw_after = real_shape_raw(True)
    summaries = iter([gradebook(False), gradebook(True)])
    raws = iter([raw_before, raw_after])
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: next(summaries))
    seen_ambitos = []
    def fake_get_criteria(**kwargs):
        seen_ambitos.append(kwargs.get("id_ambito"))
        return next(raws)
    monkeypatch.setattr(c, "get_criteria", fake_get_criteria)
    sent = {}
    def fake_request(method, path, **kwargs):
        assert method == "POST"
        assert path == "/lms/api/HyoClaseContenido/insertar"
        sent.update(copy.deepcopy(kwargs["json"]))
        return {"json": {"estado": 1}}
    monkeypatch.setattr(c, "_request", fake_request)

    result = c.upsert_criteria_verified(
        class_id=2030, class_period_id=6305, root_content_id=119598, id_ambito=518,
        records=[{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3,
                  "ABREVIATURA": "AREAS PERIM."}],
        replica={},
        expected=[{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
        verification_attempts=1,
    )
    assert result["saved"] is True
    assert result["mode"] == "ui-native-coursecode-roster-v0.7.12"
    assert seen_ambitos == [518, 518]
    assert sent["idClase"] == 2030
    assert "datosReplica" not in sent
    assert len(sent["registros"]) == 2  # raíz: competencia + plaza vacía, NO +1
    new = c._find_tree_nodes(sent["registros"], description="AREAS PERIM.",
                             parent_id=133731, level=3)
    assert len(new) == 1
    assert new[0][1]["flExiste"] is False
    assert new[0][1]["ID_CONTENIDO"] is None
    assert new[0][1]["LLAVE"] == "5-2_4-1_3-3_2-1"


def test_e0006_still_blocks_without_post_verification_or_grades(monkeypatch):
    c = SieWebClient()
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: gradebook(False))
    monkeypatch.setattr(c, "get_criteria", lambda **kwargs: real_shape_raw(False))
    monkeypatch.setattr(c, "_request", lambda *a, **k: {"json": {"estado": 0, "codigo": "e0006"}})
    with pytest.raises(SieWebError) as exc:
        c.upsert_criteria_verified(
            class_id=2030, class_period_id=6305, root_content_id=119598, id_ambito=518,
            records=[{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3}],
            replica=[], expected=[{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
            verification_attempts=1,
        )
    assert "e0006" in str(exc.value)
