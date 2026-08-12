from __future__ import annotations

import json
from pathlib import Path

import typer

from .excel_mapper_v8 import fill_excel_v8
from .models import ProductIdentity, ProductRecord
from .pipeline import ProductPipeline

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command("scrape")
def scrape(
    url: str = typer.Option(...),
    mpn: str = typer.Option(None),
    ean: str = typer.Option(None),
    upc: str = typer.Option(None),
    gtin: str = typer.Option(None),
    model: str = typer.Option(None),
    brand: str = typer.Option(None),
    name: str = typer.Option(None),
    capacity: str = typer.Option(None),
    official_domain: str = typer.Option(None, help="Dominio del fabricante."),
    output: str = typer.Option("output/product.json"),
    no_pdfs: bool = False,
    no_images: bool = False,
    no_browser_fallback: bool = False,
):
    expected = ProductIdentity(
        mpn=mpn, ean=ean, upc=upc, gtin=gtin, model=model,
        brand=brand, product_name=name, capacity=capacity,
    )
    rec = ProductPipeline().process_url(
        expected,
        url,
        official_domain=official_domain,
        include_pdfs=not no_pdfs,
        include_images=not no_images,
        browser_fallback=not no_browser_fallback,
    )
    ProductPipeline.save_json(rec, output)
    typer.echo(f"OK: {output} | identity={rec.identity.match_level} confidence={rec.identity.confidence} | images={len(rec.images)}")


@app.command("fill-excel")
def fill_xlsx(
    template: str = typer.Option(...),
    json_files: list[str] = typer.Option(..., "--json"),
    output: str = typer.Option("output/completado.xlsx"),
    trace: str = typer.Option("output/trazabilidad.json"),
    overwrite: bool = False,
):
    records = [ProductRecord.model_validate_json(Path(p).read_text(encoding="utf-8")) for p in json_files]
    report = fill_excel_v8(template, output, records, overwrite=overwrite, trace_path=trace)
    typer.echo(f"OK: {output} | celdas={report['summary']['written_count']} | trace={trace}")


@app.command("batch")
def batch(
    template: str = typer.Option(...),
    output_dir: str = typer.Option("output_batch"),
    overwrite: bool = True,
    part_number: list[str] = typer.Option(None, "--part-number", "-p", help="Part number explícito. Repite -p para varios."),
):
    from .batch import run_batch

    result = run_batch(
        template,
        output_dir,
        overwrite=overwrite,
        log=typer.echo,
        manual_part_numbers=part_number or None,
    )
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app()
