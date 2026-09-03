"""Тесты v1.3.0: парсинг ответов SpeechKit (без сети)."""

from secretary.stt.base import STTError
from secretary.stt.speechkit import SpeechKitProvider, parse_response


def test_parse_single_channel():
    response = {"chunks": [{"alternatives": [{"text": "Привет мир"}], "channelTag": "1"}]}
    result = parse_response(response)
    assert result.text == "Привет мир"
    assert result.utterances == []  # один канал — «спикер» не выделяем


def test_parse_multi_channel_as_speakers():
    response = {
        "chunks": [
            {"alternatives": [{"text": "Вопрос"}], "channelTag": "1"},
            {"alternatives": [{"text": "Ответ"}], "channelTag": "2"},
        ]
    }
    result = parse_response(response)
    assert result.text == "Вопрос Ответ"
    assert len(result.utterances) == 2
    assert result.utterances[0].speaker == "1"
    assert result.utterances[1].text == "Ответ"


def test_parse_skips_empty_alternatives():
    response = {"chunks": [{"alternatives": [{"text": "  "}], "channelTag": "1"}]}
    result = parse_response(response)
    assert result.text == ""
    assert result.utterances == []


def test_provider_requires_key():
    try:
        SpeechKitProvider(api_key="", folder_id="")
        assert False, "должна быть ошибка без ключа"
    except STTError:
        pass


def test_provider_requires_folder():
    try:
        SpeechKitProvider(api_key="k", folder_id="")
        assert False, "должна быть ошибка без folderId"
    except STTError:
        pass