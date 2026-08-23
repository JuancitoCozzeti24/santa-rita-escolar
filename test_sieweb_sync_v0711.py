import copy

from sieweb import SieWebClient
from test_sieweb_sync_v0710 import real_shape_raw, gradebook


EXPECTED_UI_NEW_KEYS = {
    "ABREVIATURA", "ABREV_ORIGI", "COLOR", "DESCPROGRAMA", "DESCRIPCION",
    "EDITOREG", "EXCLUIR", "ICONO", "ID_CLASE_CONTENIDO", "ID_CONTENIDO",
    "ID_CONTENIDO_REF", "ID_PROGRAMA", "INCLUSIVO", "INDICE", "INDICE_ORIGI",
    "ORDEN", "ORIGI", "PESO", "PESO_ORIGI", "SUMATIVO", "EXCLUIR_PORCENTAJE",
    "TRADUCCION", "TRAD_ORIGI", "LLAVE", "flExiste", "bloquearCriterio", "children",
}


def test_v0711_new_performance_uses_exact_sparse_ui_shape():
    c = SieWebClient()
    model = c.extract_criteria_editor_model(real_shape_raw(False))
    merged = c.merge_requested_criteria_into_editor_rows(
        model["rows"],
        [{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3,
          "ABREVIATURA": "AREAS PERIM."}],
        [{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
    )
    row = c._find_tree_nodes(
        merged["rows"], description="AREAS PERIM.", parent_id=133731, level=3
    )[0][1]
    assert set(row) == EXPECTED_UI_NEW_KEYS
    assert c._criterion_level(row) == 3  # inferido por ID_PROGRAMA=5; NIVEL no se serializa
    assert row["ID_CLASE_CONTENIDO"] is None
    assert row["ID_CONTENIDO"] is None
    assert row["ID_CONTENIDO_REF"] == 133731
    assert row["flExiste"] is False
    assert row["EDITOREG"] == 1
    assert row["LLAVE"] == "5-2_4-1_3-3_2-1"
    for forbidden in (
        "ID_CLASE", "ID_CURSO", "GRUPOCOD", "ID_CLASE_PERIODO", "NIVEL",
        "TIPO_EVA", "FL_CONCLUSION", "ORDEN_PROG",
    ):
        assert forbidden not in row


def test_v0711_omits_empty_datos_replica_from_post(monkeypatch):
    c = SieWebClient()
    raw_before = real_shape_raw(False)
    raw_after = real_shape_raw(True)
    raw_iter = iter([raw_before, raw_after])
    summary_iter = iter([gradebook(False), gradebook(True)])
    monkeypatch.setattr(c, "get_criteria", lambda **kwargs: next(raw_iter))
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: next(summary_iter))
    sent = []

    def fake_request(method, path, **kwargs):
        sent.append(copy.deepcopy(kwargs["json"]))
        return {"json": {"estado": 1}}

    monkeypatch.setattr(c, "_request", fake_request)
    result = c.upsert_criteria_verified(
        class_id=2030, class_period_id=6305, root_content_id=119598, id_ambito=518,
        records=[{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3,
                  "ABREVIATURA": "AREAS PERIM."}],
        replica=[],
        expected=[{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
        verification_attempts=1,
    )
    assert result["saved"] is True
    assert result["write_strategy"] == "ui-sparse-full-tree"
    assert len(sent) == 1
    assert "datosReplica" not in sent[0]


def test_v0711_adapts_after_e0006_only_when_re_read_confirms_absence(monkeypatch):
    c = SieWebClient()
    raw_before = real_shape_raw(False)
    raw_after = real_shape_raw(True)
    # 1) lectura inicial; 2) probe tras e0006 full-tree; 3) probe tras e0006 changed-root;
    # 4) verificación tras éxito changed-records.
    raw_iter = iter([raw_before, raw_before, raw_before, raw_after])
    summary_iter = iter([gradebook(False), gradebook(True)])
    monkeypatch.setattr(c, "get_criteria", lambda **kwargs: next(raw_iter))
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: next(summary_iter))

    responses = iter([
        {"json": {"estado": 0, "codigo": "e0006"}},
        {"json": {"estado": 0, "codigo": "e0006"}},
        {"json": {"estado": 1}},
    ])
    sent = []

    def fake_request(method, path, **kwargs):
        sent.append(copy.deepcopy(kwargs["json"]))
        return next(responses)

    monkeypatch.setattr(c, "_request", fake_request)
    result = c.upsert_criteria_verified(
        class_id=2030, class_period_id=6305, root_content_id=119598, id_ambito=518,
        records=[{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3,
                  "ABREVIATURA": "AREAS PERIM."}],
        replica=None,
        expected=[{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
        verification_attempts=1,
    )
    assert result["saved"] is True
    assert result["write_strategy"] == "ui-sparse-changed-records"
    assert [x["strategy"] for x in result["write_attempts"]] == [
        "ui-sparse-full-tree", "ui-sparse-changed-root", "ui-sparse-changed-records"
    ]
    assert [x["estado"] for x in result["write_attempts"]] == [0, 0, 1]
    assert len(sent) == 3
    assert len(sent[0]["registros"]) == 2       # árbol completo
    assert len(sent[1]["registros"]) == 1       # solo la competencia que contiene el cambio
    assert len(sent[2]["registros"]) == 1       # solo la fila nueva
    assert sent[2]["registros"][0]["DESCRIPCION"] == "AREAS PERIM."
    assert sent[2]["registros"][0]["ID_CONTENIDO_REF"] == 133731
    assert all("datosReplica" not in payload for payload in sent)


def test_v0711_never_falls_back_after_ambiguous_non_e0006_failure(monkeypatch):
    c = SieWebClient()
    monkeypatch.setattr(c, "get_criteria", lambda **kwargs: real_shape_raw(False))
    monkeypatch.setattr(c, "get_gradebook_summary", lambda **kwargs: gradebook(False))
    calls = []

    def fake_request(method, path, **kwargs):
        calls.append(copy.deepcopy(kwargs["json"]))
        return {"json": {"estado": 0, "codigo": "otro_error"}}

    monkeypatch.setattr(c, "_request", fake_request)
    try:
        c.upsert_criteria_verified(
            class_id=2030, class_period_id=6305, root_content_id=119598, id_ambito=518,
            records=[{"descripcion": "AREAS PERIM.", "idpadre": 133731, "nivelEva": 3}],
            replica=None,
            expected=[{"description": "AREAS PERIM.", "parent_id": 133731, "level": 3}],
            verification_attempts=1,
        )
        assert False, "debió bloquear un error no e0006"
    except Exception as exc:
        assert "no es seguro probar otra forma" in str(exc)
    assert len(calls) == 1
