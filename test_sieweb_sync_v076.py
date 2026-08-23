from sieweb import SieWebClient, SieWebError


def test_exact_criterion_ignores_accents_and_spacing():
    c = SieWebClient()
    summary={"criteria":[{"id":33,"idpadre":22,"nivelEva":3,"descripcion":"Comunica  procedimientos y unidades"}]}
    got=c.find_exact_criterion(summary, description="Comunica procedimientos y unidades", parent_id=22, level=3)
    assert [x["id"] for x in got] == [33]


def test_achievement_level_is_protected():
    c = SieWebClient()
    summary={"criteria":[{"id":1,"nivelEva":1,"descripcion":"Nivel de Logro"},{"id":3,"nivelEva":3,"descripcion":"Desempeño"}]}
    try:
        c.assert_performance_target(summary, header_id=1, performance_level=3)
        assert False, "debió bloquear Nivel de Logro"
    except SieWebError as exc:
        assert "PROTECCIÓN NIVEL DE LOGRO" in str(exc)
    assert c.assert_performance_target(summary, header_id=3, performance_level=3)["id"] == 3


def test_new_performance_record_clones_destination_sibling(monkeypatch):
    c=SieWebClient()
    raw={"json":{"rows":[{"id":99,"idClaseContenido":88,"idpadre":22,"nivelEva":3,"descripcion":"Anterior","peso":100,"activo":True}]}}
    monkeypatch.setattr(c,"get_criteria",lambda **kwargs: raw)
    rec=c.build_new_performance_record(class_id=1,class_period_id=2,root_content_id=3,parent_id=22,description="Áreas y perímetros",level=3)
    assert rec["DESCRIPCION"] == "Áreas y perímetros"
    assert rec["ID_CONTENIDO_REF"] == 22
    assert c._criterion_level(rec) == 3
    assert rec["ID_CONTENIDO"] is None and rec["ID_CLASE_CONTENIDO"] is None
    assert rec["flExiste"] is False and rec["EDITOREG"] == 1
    assert "ID_CLASE" not in rec and "ID_CLASE_PERIODO" not in rec
    assert "activo" not in rec
