---
name: openai-project-llm
description: Standardize OpenAI API integration in code projects with prompt.json, prompt_manager, llm_client, .env configuration, template-based prompt rendering, response_format support, and dict-based post-processing. Use when a coding task needs to add or refactor reusable large-model calling capabilities through API key based OpenAI or OpenAI-compatible endpoints.
---

# OpenAI Project LLM

Follow these rules when a coding task needs reusable OpenAI calling capability inside a project.

## Core Workflow

1. Check whether the project already has `prompt.json`, `prompt_manager`, `llm_client`, and result post-processing helpers.
2. If any required module is missing, create the missing files instead of scattering ad hoc prompt strings through business code.
3. If the project already has the required modules, add only a thin calling interface and reuse the existing implementation style.

## Required Project Conventions

- Keep a project-level `prompt.json` file for global prompts.
- Use the prompt structure `{"promptKey": {"zh": "", "en": ""}}`.
- Accept `prompt_key`, `lang`, and prompt template parameters as the primary inputs of the LLM call interface.
- Render prompt variables with `{{variable_name}}` placeholders.
- Support an optional `response_format` parameter.
- Default to JSON output when `response_format` is not explicitly provided.
- Return a post-processed `dict` object from the shared client layer.
- Manage `OPENAI_API_KEY`, URL, model, and timeout settings through `.env`.

## Recommended Module Layout

- `prompt_manager`: load `prompt.json`, select localized prompts, validate missing keys, and render templates.
- `llm_client`: read `.env`, build the OpenAI request, submit the API call, and hand the raw response to a post-processor.
- `llm_post_processor`: parse model output and normalize the final result into a `dict`.
- `llm_service` or similar facade: expose a single reusable method for business modules.

## Parameter Handling

- Put optional inference parameters such as `temperature`, `top_p`, `top_k`, `top_n`, and token limits behind a shared `extract_param` helper.
- Only pass through supported parameters that have non-null values.
- Keep the business-facing method signature simple and stable.

## Implementation Notes

- Prefer a project-local prompt manager over inline string concatenation.
- Prefer deterministic JSON parsing paths whenever the caller does not require plain text.
- Fail fast on missing prompt keys, missing template variables, or missing API credentials.
- Keep transport code isolated so tests can stub network calls cleanly.

