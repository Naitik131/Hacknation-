"""One function, two providers. Switch with LLM_PROVIDER=anthropic|openai."""
import os

from pydantic import BaseModel

PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")


def structured(prompt: str, schema: type[BaseModel]) -> BaseModel:
    if PROVIDER == "openai":
        from openai import OpenAI
        r = OpenAI().chat.completions.parse(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            response_format=schema,
            messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.parsed or schema()
    import anthropic
    r = anthropic.Anthropic().messages.create(
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=4096,
        # forced tool call = schema-constrained JSON output
        tools=[{"name": "record", "description": "Record the extraction result.",
                "input_schema": schema.model_json_schema()}],
        tool_choice={"type": "tool", "name": "record"},
        messages=[{"role": "user", "content": prompt}])
    block = next(b for b in r.content if b.type == "tool_use")
    return schema.model_validate(block.input)
