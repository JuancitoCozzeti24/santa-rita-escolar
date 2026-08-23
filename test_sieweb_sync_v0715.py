from sieweb import SieWebClient


def test_v0715_gradebook_reads_full_roster_without_false_individual_filter(monkeypatch):
    c=SieWebClient()
    seen={}

    def request(method,path,**kwargs):
        seen.update(kwargs["params"])
        return {"json":{}}

    monkeypatch.setattr(c,"_request",request)
    c.get_gradebook(class_period_id=6305,root_content_id=119598)
    assert "objInfoRegIndividual[alucod]" not in seen
    assert seen["objInfoRegIndividual[tipoRegistro]"] == "registroNotas"
    assert seen["chkNotFRET"] is False


def test_v0715_explicit_individual_read_can_supply_real_student_code(monkeypatch):
    c=SieWebClient()
    seen={}

    def request(method,path,**kwargs):
        seen.update(kwargs["params"])
        return {"json":{}}

    monkeypatch.setattr(c,"_request",request)
    c.get_gradebook(
        class_period_id=6305,root_content_id=119598,
        extra_params={
            "objInfoRegIndividual[alucod]":"A20180042",
            "objInfoRegIndividual[tipoRegistro]":"registroNotasIndividual",
        },
    )
    assert seen["objInfoRegIndividual[alucod]"] == "A20180042"
    assert seen["objInfoRegIndividual[tipoRegistro]"] == "registroNotasIndividual"
