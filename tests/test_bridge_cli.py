import asyncio
from argparse import Namespace

from cli import bridge_runtime, mac_cli, phone_client


class FakePhoneClient:
    def __init__(self, *args, **kwargs):
        pass

    async def aclose(self):
        pass

    async def chat(self, **kwargs):
        yield "hello from phone"


def test_legacy_one_shot_cli_writes_streamed_response_to_stdout(monkeypatch, capsys):
    monkeypatch.setattr(phone_client, "PhoneClient", FakePhoneClient)
    args = Namespace(
        phone_url="http://127.0.0.1:9090",
        host=None,
        port=None,
        save_config=False,
        model=None,
        api_key=None,
        allow_write=False,
        allow_shell=False,
        prompt="test",
        session=None,
    )

    asyncio.run(mac_cli.cmd_chat_async(args, {}))

    assert "hello from phone" in capsys.readouterr().out


def test_new_bridge_cli_has_expected_management_commands():
    parser = bridge_runtime.build_parser()
    assert parser.parse_args(["models"]).command == "models"
    assert parser.parse_args(["start", "model.gguf", "--threads", "4"]).threads == 4
    assert parser.parse_args(["run", "hello"]).prompt == "hello"
