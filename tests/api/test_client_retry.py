"""Edge case tests for api/client retry + error paths."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from wodplanner.api.client import WodAppClient, WodAppError


class _Resp:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("e", request=MagicMock(), response=self)


class TestRetryEdges:
    @patch("wodplanner.api.client.httpx.Client")
    @patch("wodplanner.api.client.time.sleep")
    def test_503_then_success(self, mock_sleep, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = [
            _Resp({}, status_code=503),
            _Resp({
                "status": "OK",
                "id_user": 1,
                "username": "u",
                "firstname": "F",
                "token": "t",
                "gyms": [{"id_gym": 1, "idc": 1, "name": "G", "city": "C"}],
            }),
            _Resp({"status": "OK", "resultset": [{"id_agenda": 7}]}),
        ]
        client = WodAppClient()
        session = client.login("u", "p")
        assert session.token == "t"
        assert mock_client.post.call_count == 3

    @patch("wodplanner.api.client.httpx.Client")
    def test_transport_error_raises_wodapp_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.side_effect = httpx.TransportError("net down")
        with pytest.raises(WodAppError, match="Cannot reach"):
            WodAppClient().login("u", "p")

    @patch("wodplanner.api.client.httpx.Client")
    def test_status_not_ok_raises_wodapp_error(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = _Resp({
            "status": "ERROR",
            "notice": "bad pass",
        })
        with pytest.raises(WodAppError, match="API error: bad pass"):
            WodAppClient().login("u", "p")

    @patch("wodplanner.api.client.httpx.Client")
    def test_non_retry_status_raises_immediately(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.post.return_value = _Resp({}, status_code=400)
        with pytest.raises(WodAppError, match="status 400"):
            WodAppClient().login("u", "p")
