"""
Corvin interactive operator shell.

Start with:
    corvin
    python -m apps.cli.main

Commands available inside the shell:
    investigate   Run a full investigation for a service.
    list          Show all investigations (newest first).
    show <id>     Display full RCA and fix strategy for an investigation.
    health        Check API reachability.
    clear         Clear the terminal.
    help          Show available commands.
    exit / quit   Exit the shell.
"""

from __future__ import annotations

import os
import shlex
import textwrap
from typing import Any

import httpx
import pyfiglet
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich import box

# ── Globals ───────────────────────────────────────────────────────────────────

console = Console()
API_URL = os.environ.get("METGUARD_API_URL", "http://localhost:8000")
TIMEOUT = float(os.environ.get("METGUARD_CLI_TIMEOUT", "120"))

# ── Helpers ───────────────────────────────────────────────────────────────────

CONFIDENCE_COLOUR = {"high": "green", "medium": "yellow", "low": "red"}
RISK_COLOUR = {"low": "green", "medium": "yellow", "high": "red"}


def _api_get(path: str, timeout: float = 30) -> Any:
    resp = httpx.get(f"{API_URL}{path}", timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _api_post(path: str, payload: dict, timeout: float = TIMEOUT) -> Any:
    resp = httpx.post(f"{API_URL}{path}", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _truncate(text: str, width: int = 80) -> str:
    return textwrap.shorten(text, width=width, placeholder="…")


# ── Command handlers ──────────────────────────────────────────────────────────


def cmd_help() -> None:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Command", style="bold")
    table.add_column("Description")
    table.add_row("investigate", "Start a new investigation — prompts for service, env, description")
    table.add_row("list", "List all investigations, newest first")
    table.add_row("show <id>", "Show full RCA + fix strategy for an investigation")
    table.add_row("health", "Check Corvin API reachability")
    table.add_row("clear", "Clear the terminal")
    table.add_row("help", "Show this help")
    table.add_row("exit / quit", "Exit the shell")
    console.print(table)


def cmd_health() -> None:
    try:
        data = _api_get("/health")
        console.print(f"  [green]✓[/green] API is reachable — status: [bold]{data.get('status')}[/bold]")
    except httpx.ConnectError:
        console.print(f"  [red]✗[/red] Cannot connect to Corvin API at [bold]{API_URL}[/bold]")
    except Exception as exc:
        console.print(f"  [red]✗[/red] {exc}")


def cmd_investigate(args: list[str]) -> None:
    # Parse optional inline args: investigate <service> [env] [description]
    service = args[0] if len(args) > 0 else None
    environment = args[1] if len(args) > 1 else None
    description = " ".join(args[2:]) if len(args) > 2 else None

    # Interactive prompts for anything not supplied inline
    if not service:
        service = console.input("  Service name: ").strip()
    if not service:
        console.print("  [red]Service name is required.[/red]")
        return
    if not environment:
        environment = console.input("  Environment [production]: ").strip() or "production"
    if not description:
        description = console.input("  Description [Manual CLI investigation]: ").strip() \
                      or "Manual CLI investigation"

    console.print()
    with console.status(f"[bold cyan]Running investigation for [white]{service}[/white] / {environment}…[/bold cyan]"):
        try:
            post_data = _api_post(
                "/investigations/",
                {"service_name": service, "environment": environment, "description": description},
            )
        except httpx.ConnectError:
            console.print(f"  [red]✗[/red] Cannot connect to Corvin API at [bold]{API_URL}[/bold]")
            return
        except httpx.HTTPStatusError as exc:
            console.print(f"  [red]✗[/red] API error {exc.response.status_code}: {exc.response.text[:200]}")
            return

    request_id = post_data.get("request_id", "")

    # Fetch full result for immediate display
    try:
        result = _api_get(f"/investigations/{request_id}")
    except Exception:
        result = {}

    _render_result(result, request_id)


def cmd_list() -> None:
    try:
        items = _api_get("/investigations/")
    except httpx.ConnectError:
        console.print(f"  [red]✗[/red] Cannot connect to Corvin API at [bold]{API_URL}[/bold]")
        return
    except Exception as exc:
        console.print(f"  [red]✗[/red] {exc}")
        return

    if not items:
        console.print("  [dim]No investigations found. Run [bold]investigate[/bold] to start one.[/dim]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan", min_width=90)
    table.add_column("#", style="dim", width=3)
    table.add_column("Service", style="bold")
    table.add_column("Environment")
    table.add_column("Trigger")
    table.add_column("Completed", style="dim")
    table.add_column("ID", style="dim")

    for i, inv in enumerate(items, 1):
        completed = inv.get("completed_at", "")[:19].replace("T", " ")
        table.add_row(
            str(i),
            inv.get("service_name", ""),
            inv.get("environment", ""),
            inv.get("trigger_source", "").replace("_", " "),
            completed,
            inv.get("request_id", "")[:8] + "…",
        )

    console.print(table)
    console.print(f"  [dim]Use [bold]show <id>[/bold] for full details. Showing first 8 chars of ID.[/dim]")


def cmd_show(args: list[str]) -> None:
    if not args:
        console.print("  [red]Usage:[/red] show <request_id>")
        return
    request_id = args[0]
    try:
        result = _api_get(f"/investigations/{request_id}")
    except httpx.ConnectError:
        console.print(f"  [red]✗[/red] Cannot connect to Corvin API at [bold]{API_URL}[/bold]")
        return
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            console.print(f"  [red]✗[/red] Investigation [bold]{request_id!r}[/bold] not found.")
        else:
            console.print(f"  [red]✗[/red] API error {exc.response.status_code}")
        return
    _render_result(result, request_id)


def _render_result(result: dict, request_id: str) -> None:
    req = result.get("request", {})
    rca = result.get("rca") or {}
    fix = result.get("fix_strategy") or {}

    # ── Header ────────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel(
        f"[bold white]{req.get('service_name', '?')}[/bold white]  "
        f"[dim]{req.get('environment', '?')}[/dim]  "
        f"[dim cyan]{req.get('trigger_source', '').replace('_', ' ')}[/dim cyan]",
        title="[bold cyan]Corvin Investigation[/bold cyan]",
        subtitle=f"[dim]{request_id}[/dim]",
        border_style="cyan",
        padding=(0, 1),
    ))

    # ── RCA ───────────────────────────────────────────────────────────────────
    confidence = rca.get("confidence", "unknown")
    conf_colour = CONFIDENCE_COLOUR.get(confidence, "white")

    console.print(Rule("[bold]Root Cause Analysis[/bold]", style="cyan"))
    console.print(f"  [bold]Confidence[/bold]  [{conf_colour}]{confidence.upper()}[/{conf_colour}]")
    console.print(f"  [bold]Summary[/bold]     {rca.get('summary', '(not available)')}")
    console.print(f"  [bold]Root Cause[/bold]  {rca.get('root_cause', '(not available)')}")

    factors = rca.get("contributing_factors") or []
    if factors:
        console.print("  [bold]Factors[/bold]")
        for f in factors:
            console.print(f"    [dim]•[/dim] {f}")

    # ── Fix Strategy ──────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold]Fix Strategy[/bold]", style="cyan"))
    console.print(f"  [bold]Summary[/bold]        {fix.get('summary', '(not available)')}")
    console.print(f"  [bold]Justification[/bold]  {fix.get('justification', '(not available)')}")

    actions = fix.get("actions") or []
    if actions:
        console.print()
        console.print("  [bold]Recommended Actions[/bold]  [dim](all require human approval in V1)[/dim]")
        for i, action in enumerate(actions, 1):
            risk = action.get("risk_level", "unknown")
            risk_colour = RISK_COLOUR.get(risk, "white")
            console.print(
                f"  [dim]{i}.[/dim] [bold]{action.get('title')}[/bold]  "
                f"[{risk_colour}][{risk.upper()} RISK][/{risk_colour}]"
            )
            console.print(f"     {action.get('description', '')}")
            console.print(f"     [dim]Impact: {action.get('estimated_impact', '')}[/dim]")
    else:
        console.print("  [dim]No specific actions proposed.[/dim]")

    console.print()


# ── Shell entry point ─────────────────────────────────────────────────────────


def _print_banner() -> None:
    art = pyfiglet.figlet_format("CORVIN", font="standard").rstrip()
    console.print()
    console.rule(style="cyan")
    console.print()
    console.print(art, style="bold cyan", highlight=False, markup=False)
    console.print()
    console.print("  Azure-native investigation platform  [dim cyan]·  v1[/dim cyan]")
    console.print()
    console.print(
        "  [bold white]help[/bold white] [dim]— commands[/dim]   "
        "[bold white]Ctrl+C[/bold white] [dim]— cancel[/dim]   "
        "[bold white]exit[/bold white] [dim]— quit[/dim]"
    )
    console.print()
    console.rule(style="cyan")


def run_shell(api_url: str = API_URL) -> None:
    """Entry point for the interactive shell. api_url is injectable for tests."""
    global API_URL
    API_URL = api_url

    _print_banner()
    cmd_health()
    console.print()

    session: PromptSession = PromptSession(
        history=InMemoryHistory(),
        auto_suggest=AutoSuggestFromHistory(),
    )

    while True:
        # ── Prompt ────────────────────────────────────────────────────────────
        try:
            raw = session.prompt(HTML("<ansibrightcyan>corvin</ansibrightcyan><ansicyan>›</ansicyan> "))
        except KeyboardInterrupt:
            # Ctrl+C at blank prompt — hint the user
            console.print("  [dim]^C  (type [bold]exit[/bold] to quit)[/dim]")
            continue
        except EOFError:
            console.print("\n  [dim]Goodbye.[/dim]")
            break

        line = raw.strip()
        if not line:
            continue

        try:
            tokens = shlex.split(line)
        except ValueError:
            tokens = line.split()

        cmd = tokens[0].lower()
        args = tokens[1:]

        # ── Dispatch — Ctrl+C here cancels only the current command ───────────
        try:
            if cmd in ("exit", "quit"):
                console.print("  [dim]Goodbye.[/dim]")
                break
            elif cmd == "help":
                cmd_help()
            elif cmd == "health":
                cmd_health()
            elif cmd == "investigate":
                cmd_investigate(args)
            elif cmd == "list":
                cmd_list()
            elif cmd == "show":
                cmd_show(args)
            elif cmd == "clear":
                # os.system cls/clear wipes the scroll buffer; console.clear() only moves the
                # cursor and leaves scroll history that reflows on terminal resize.
                os.system("cls" if os.name == "nt" else "clear")
                _print_banner()
            else:
                console.print(
                    f"  [red]Unknown command:[/red] [bold]{cmd}[/bold]  "
                    f"[dim](type [bold]help[/bold] for available commands)[/dim]"
                )
        except KeyboardInterrupt:
            console.print("\n  [yellow]Cancelled.[/yellow]")


# ── Typer shim — keeps `corvin` entry point working ─────────────────────────

import typer  # noqa: E402 — kept at bottom to avoid polluting the module namespace

app = typer.Typer(invoke_without_command=True, add_completion=False)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="Corvin API base URL.",
        envvar="METGUARD_API_URL",
    ),
) -> None:
    """Corvin interactive operator shell."""
    if ctx.invoked_subcommand is None:
        run_shell(api_url=api_url)


if __name__ == "__main__":
    app()
