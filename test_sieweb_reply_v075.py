from __future__ import annotations

from copy import deepcopy

import pytest

from sieweb import SieWebClient, SieWebError


MESSAGE_ID = 472538


def detail_with_reply_context():
    return {
        "json": {
            "idMensaje": MESSAGE_ID,
            "asunto": "Justificación de falta.",
            "idEdition": 880321,
            "remitente": {
                "USUCOD": "A20140042",
                "USUNOM": "DE TOMÁS PERALTA, Gianella Nikol",
            },
        }
    }


class FakeReplyClient(SieWebClient):
    def __init__(self, detail=None, send_result=None):
        super().__init__()
        self.detail = deepcopy(detail if detail is not None else detail_with_reply_context())
        self.send_result = deepcopy(
            send_result if send_result is not None
            else {"json": {"estado": 1, "idMensaje": 990001, "mensaje": "OK"}}
        )
        self.read_calls = []
        self.sent_payload = None

    def get_message(self, message_id: int, folder_id: int = 1):
        self.read_calls.append((message_id, folder_id))
        return deepcopy(self.detail)

    def _request(self, method, path, *, params=None, json=None):
        assert method == "POST"
        assert path == "/lms/api/HyoMensajeria/enviarMensaje"
        self.sent_payload = deepcopy(json)
        return deepcopy(self.send_result)


def test_prepare_reply_uses_real_thread_context_and_numeric_edition_id():
    client = FakeReplyClient()
    prepared = client.prepare_reply(
        reply_to_message_id=MESSAGE_ID,
        html_message="<p>Gracias por informar.</p>",
    )

    assert client.read_calls == [(MESSAGE_ID, 1)]
    assert prepared["recipients"] == ["A20140042"]
    assert prepared["subject"] == "Justificación de falta."
    assert prepared["edition_id"] == 880321
    assert prepared["edition_id_source"] == "detail"
    assert prepared["payload"]["idEdition"] == 880321
    assert isinstance(prepared["payload"]["idEdition"], int)
    assert prepared["payload"]["response"] == 1


def test_prepare_reply_falls_back_to_original_numeric_message_id_with_explicit_context():
    client = FakeReplyClient(detail={"json": {"idMensaje": MESSAGE_ID}})
    prepared = client.prepare_reply(
        reply_to_message_id=MESSAGE_ID,
        html_message="<p>Respuesta.</p>",
        recipient_codes=["F20240001"],
        subject="Equivocación",
        folder_id=1,
    )

    assert prepared["edition_id"] == MESSAGE_ID
    assert prepared["edition_id_source"] == "message_id"
    assert prepared["payload"]["idEdition"] == MESSAGE_ID
    assert isinstance(prepared["payload"]["idEdition"], int)
    assert prepared["recipients"] == ["F20240001"]
    assert prepared["subject"] == "Equivocación"


def test_send_reply_never_claims_success_when_sieweb_returns_e0001_estado_zero():
    client = FakeReplyClient(
        send_result={"json": {"estado": 0, "mensaje": "e0001"}}
    )

    with pytest.raises(SieWebError) as exc_info:
        client.send_reply(
            reply_to_message_id=MESSAGE_ID,
            html_message="<p>Respuesta que no debe figurar como enviada.</p>",
        )

    text = str(exc_info.value)
    assert "estado=0" in text
    assert "e0001" in text
    assert "No se marcará como enviada" in text
    assert isinstance(client.sent_payload["idEdition"], int)


def test_send_reply_returns_structured_success_only_for_estado_one():
    client = FakeReplyClient()
    result = client.send_reply(
        reply_to_message_id=MESSAGE_ID,
        html_message="<p>Respuesta correcta.</p>",
    )

    assert result["sent"] is True
    assert result["status_code"] == 1
    assert result["message_id"] == 990001
    assert result["reply_to_message_id"] == MESSAGE_ID
    assert result["edition_id"] == 880321
    assert result["recipients"] == ["A20140042"]
    assert result["subject"] == "Justificación de falta."


def test_prepare_reply_does_not_guess_a_global_usucod_from_unrelated_data():
    client = FakeReplyClient(
        detail={
            "json": {
                "idMensaje": MESSAGE_ID,
                "asunto": "Equivocación",
                "destinatarios": [{"USUCOD": "JB RINGAS"}],
            }
        }
    )

    with pytest.raises(SieWebError) as exc_info:
        client.prepare_reply(
            reply_to_message_id=MESSAGE_ID,
            html_message="<p>Respuesta.</p>",
        )

    assert "USUCOD del remitente" in str(exc_info.value)
    assert client.sent_payload is None
