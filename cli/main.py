"""CLI tool for the Spreadsheet Analysis Service."""

import sys
import time
from pathlib import Path

import click
import requests

DEFAULT_API = "http://localhost:8080"


def api_url(ctx):
    return ctx.obj["api"]


def handle_error(response):
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        click.secho(f"Error ({response.status_code}): {detail}", fg="red", err=True)
        sys.exit(1)


@click.group()
@click.option("--api", default=DEFAULT_API, envvar="SA_API_URL", help="API base URL")
@click.pass_context
def cli(ctx, api):
    """Spreadsheet Analysis Service CLI."""
    ctx.ensure_object(dict)
    ctx.obj["api"] = api.rstrip("/")


@cli.command()
@click.option("--file", "-f", "filepath", required=True, type=click.Path(exists=True), help="CSV or Excel file")
@click.option("--question", "-q", required=True, help="Question about the data")
@click.pass_context
def submit(ctx, filepath, question):
    """Submit a job: upload file + question, print job_id."""
    with open(filepath, "rb") as f:
        r = requests.post(
            f"{api_url(ctx)}/jobs",
            files={"file": (Path(filepath).name, f)},
            data={"question": question},
        )
    handle_error(r)
    job_id = r.json()["job_id"]
    click.echo(job_id)


@cli.command()
@click.argument("job_id")
@click.pass_context
def status(ctx, job_id):
    """Check job status."""
    r = requests.get(f"{api_url(ctx)}/jobs/{job_id}/status")
    handle_error(r)
    data = r.json()
    color = {"pending": "yellow", "processing": "blue", "completed": "green", "failed": "red"}.get(data["status"], "white")
    click.secho(data["status"], fg=color)
    if data.get("error"):
        click.secho(f"  Error: {data['error']}", fg="red")


@cli.command()
@click.argument("job_id")
@click.option("--download-charts", "-d", is_flag=True, help="Download chart artifacts to current directory")
@click.pass_context
def results(ctx, job_id, download_charts):
    """Get job results: answer, code, charts."""
    r = requests.get(f"{api_url(ctx)}/jobs/{job_id}/results")
    handle_error(r)
    data = r.json()

    for msg in data["messages"]:
        role_color = "cyan" if msg["role"] == "user" else "green"
        click.secho(f"\n[{msg['role'].upper()}]", fg=role_color, bold=True)
        click.echo(msg["content"])
        if msg.get("thinking"):
            click.secho("\n--- thinking ---", fg="bright_black")
            click.echo(msg["thinking"][:500])
            if len(msg["thinking"]) > 500:
                click.secho("  ... (truncated)", fg="bright_black")
            click.secho("--- end thinking ---", fg="bright_black")
        if msg.get("code"):
            click.secho("\n--- code ---", fg="bright_black")
            click.echo(msg["code"])
            click.secho("--- end ---", fg="bright_black")
        if msg.get("execution_output"):
            click.secho(f"stdout: {msg['execution_output']}", fg="bright_blue")

    if data["artifacts"]:
        click.echo()
        for art in data["artifacts"]:
            click.echo(f"  [{art['type']}] {art['filename']}")
            if download_charts and art.get("url"):
                url = f"{api_url(ctx)}{art['url']}"
                resp = requests.get(url)
                if resp.ok:
                    dest = Path(art["filename"])
                    dest.write_bytes(resp.content)
                    click.secho(f"    -> saved to {dest}", fg="green")


@cli.command()
@click.argument("job_id")
@click.option("--question", "-q", required=True, help="Follow-up question")
@click.pass_context
def followup(ctx, job_id, question):
    """Submit a follow-up question against an existing job."""
    r = requests.post(
        f"{api_url(ctx)}/jobs/{job_id}/followup",
        data={"question": question},
    )
    handle_error(r)
    click.secho("Follow-up submitted", fg="green")
    click.echo(r.json()["job_id"])


@cli.command()
@click.option("--file", "-f", "filepath", required=True, type=click.Path(exists=True), help="CSV or Excel file")
@click.option("--question", "-q", required=True, help="Question about the data")
@click.option("--download-charts", "-d", is_flag=True, help="Download chart artifacts")
@click.pass_context
def ask(ctx, filepath, question, download_charts):
    """Submit, poll, and print results in one step."""
    # Submit
    with open(filepath, "rb") as f:
        r = requests.post(
            f"{api_url(ctx)}/jobs",
            files={"file": (Path(filepath).name, f)},
            data={"question": question},
        )
    handle_error(r)
    job_id = r.json()["job_id"]
    click.secho(f"Job submitted: {job_id}", fg="bright_black")

    # Poll
    spinner = [".", "..", "..."]
    i = 0
    while True:
        r = requests.get(f"{api_url(ctx)}/jobs/{job_id}/status")
        handle_error(r)
        s = r.json()["status"]
        click.echo(f"\r  Processing{spinner[i % 3]}   ", nl=False)
        if s in ("completed", "failed"):
            click.echo()
            break
        time.sleep(1.5)
        i += 1

    # Results
    ctx.invoke(results, job_id=job_id, download_charts=download_charts)


if __name__ == "__main__":
    cli()
