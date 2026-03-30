from pathlib import Path

import pytest

from billing_dsl_agent.services.prompt_manager import PromptManager, PromptManagerError


def test_prompt_manager_renders_template_placeholders(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    prompt_path.write_text(
        '{"demo":{"zh":"你好，{{name}}。任务：{{task}}","en":"Hello, {{name}}. Task: {{task}}"}}',
        encoding="utf-8",
    )

    manager = PromptManager(prompt_path=prompt_path)
    prompt = manager.render_prompt(
        prompt_key="demo",
        lang="zh",
        params={"name": "Alice", "task": "生成 DSL"},
    )

    assert prompt == "你好，Alice。任务：生成 DSL"


def test_prompt_manager_raises_on_missing_template_params(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    prompt_path.write_text('{"demo":{"zh":"你好，{{name}}"}}', encoding="utf-8")

    manager = PromptManager(prompt_path=prompt_path)

    with pytest.raises(PromptManagerError) as exc_info:
        manager.render_prompt(prompt_key="demo", lang="zh", params={})

    assert "name" in str(exc_info.value)


def test_prompt_manager_falls_back_to_zh_when_lang_missing(tmp_path: Path) -> None:
    prompt_path = tmp_path / "prompt.json"
    prompt_path.write_text('{"demo":{"zh":"你好，{{name}}"}}', encoding="utf-8")

    manager = PromptManager(prompt_path=prompt_path)
    prompt = manager.render_prompt(prompt_key="demo", lang="en", params={"name": "Bob"})

    assert prompt == "你好，Bob"

