# Typer CLI entrypoint for Stage 1 extraction command.
from __future__ import annotations

import json
from pathlib import Path

import typer
from dotenv import load_dotenv

from pipeline_qa_extractor.extractor import PipelineExtractor
from pipeline_qa_extractor.models import ExtractionConfig, Technology
from pipeline_qa_extractor.prompts import PROMPT_VERSION

app = typer.Typer(add_completion=False)


@app.command("extract")
def extract_command(
    pipeline_file: str = typer.Option(..., "--pipeline-file", exists=True, readable=True),
    dag_file: str | None = typer.Option(None, "--dag-file", exists=True, readable=True),
    technology: Technology = typer.Option(..., "--technology", help="databricks or postgres"),
    model: str = typer.Option("openai/gpt-4.1-mini", "--model"),
    output: str = typer.Option(..., "--output"),
    force: bool = typer.Option(False, "--force"),
    print_cost: bool = typer.Option(False, "--print-cost"),
    raw_output_dir: str | None = typer.Option(None, "--raw-output-dir"),
    max_input_chars: int = typer.Option(80000, "--max-input-chars"),
) -> None:
    load_dotenv()

    config = ExtractionConfig(
        pipeline_file=pipeline_file,
        dag_file=dag_file,
        technology=technology,
        model=model,
        output=output,
        force=force,
        print_cost=print_cost,
        raw_output_dir=raw_output_dir,
        max_input_chars=max_input_chars,
        prompt_version=PROMPT_VERSION,
    )

    extractor = PipelineExtractor()
    result = extractor.run(config)

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump()
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    typer.echo(str(output_path))

    if print_cost:
        usage = result.llm_usage
        typer.echo(
            json.dumps(
                {
                    "model": config.model,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "cached_tokens": usage.cached_tokens,
                    "actual_cost_usd": usage.actual_cost_usd,
                    "estimated_cost_usd": usage.estimated_cost_usd,
                    "cost_source": usage.cost_source,
                    "pricing_snapshot": usage.pricing_snapshot,
                },
                indent=2,
                sort_keys=True,
            )
        )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
