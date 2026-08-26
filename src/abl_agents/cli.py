"""Interactive terminal demo of the ABL agentic lifecycle system."""
from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import audit_log, config, deal_store, knowledge_base, registry, tools
from .orchestrator import DealWorkflow

console = Console()


def _select_deal_id() -> str:
    deals = deal_store.list_deals()
    if len(deals) == 1:
        return deals[0]["deal_id"]
    console.print("[bold]Available deals:[/bold]")
    for d in deals:
        console.print(f"  {d['deal_id']} - {d['borrower']['name']}")
    return Prompt.ask("Deal ID", default=deals[0]["deal_id"])


def _print_deal_snapshot(deal_id: str) -> None:
    deal = deal_store.get_deal(deal_id)
    facility = deal["facility"]
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("Borrower", f"{deal['borrower']['name']} ({deal['borrower']['industry']})")
    table.add_row("Facility", f"{facility['type']} - ${facility['commitment']:,.0f} commitment")
    table.add_row("Stage", deal["stage"])
    table.add_row("Risk rating", f"{deal['risk_rating']}" + ("  [red bold](WATCHLIST)[/red bold]" if deal["watchlist"] else ""))
    table.add_row("Outstanding", f"${deal['outstanding_balance']:,.0f}")
    console.print(Panel(table, title=f"[bold]{deal_id}[/bold]", border_style="cyan"))


def _on_tool_call(name: str, tool_input: dict) -> None:
    args_preview = ", ".join(f"{k}={v!r}" for k, v in list(tool_input.items())[:3])
    console.print(f"  [dim]-> tool call: {name}({args_preview}{', ...' if len(tool_input) > 3 else ''})[/dim]")


def _approve_change_interactive(agent_name: str, change: dict) -> bool:
    body = (
        f"[bold]Field:[/bold] {change['field_path']}\n"
        f"[bold]Proposed value:[/bold] {change['new_value']}\n"
        f"[bold]Rationale:[/bold] {change['rationale']}"
    )
    console.print(Panel(body, title=f"[yellow]HITL gate - proposed by {agent_name}[/yellow]", border_style="yellow"))
    return Confirm.ask("Approve this change?", default=True)


def _print_agent_result(agent_name: str, stage_label: str, result) -> None:
    console.print(Panel(result.text.strip(), title=f"[bold green]{agent_name}[/bold green] - {stage_label}", border_style="green"))
    if result.citations:
        cites = "; ".join(f"{c['source']} > {c['title']}" for c in result.citations)
        console.print(f"[dim]Sources: {cites}[/dim]")
    console.print(f"[dim]{result.tool_calls and len(result.tool_calls) or 0} tool call(s), {result.turns_used} model turn(s)[/dim]\n")


def run_full_lifecycle(deal_id: str) -> None:
    workflow = DealWorkflow(deal_id)
    for agent_id in registry.LIFECYCLE_ORDER:
        stage_label = registry.get_stage_label(agent_id)
        agent_name = registry.get_agent(agent_id).name
        console.rule(f"[bold]{stage_label}[/bold]")
        try:
            result, _ = workflow.run_stage(agent_id, _approve_change_interactive, on_tool_call=_on_tool_call)
        except RuntimeError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            return
        _print_agent_result(agent_name, stage_label, result)
        if agent_id != registry.LIFECYCLE_ORDER[-1]:
            if not Confirm.ask("Continue to next stage?", default=True):
                break


def run_single_stage(deal_id: str) -> None:
    console.print("\n[bold]Stages:[/bold]")
    for i, agent_id in enumerate(registry.LIFECYCLE_ORDER, 1):
        console.print(f"  {i}. {registry.get_stage_label(agent_id)}")
    idx = Prompt.ask("Pick a stage number", choices=[str(i) for i in range(1, len(registry.LIFECYCLE_ORDER) + 1)])
    agent_id = registry.LIFECYCLE_ORDER[int(idx) - 1]
    workflow = DealWorkflow(deal_id)
    try:
        result, _ = workflow.run_stage(agent_id, _approve_change_interactive, on_tool_call=_on_tool_call)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        return
    _print_agent_result(registry.get_agent(agent_id).name, registry.get_stage_label(agent_id), result)


def chat_with_wiki_agent() -> None:
    agent = registry.get_agent("wiki")
    console.print(Panel(
        "Ask about ABL terms, borrowing base mechanics, covenants, the lifecycle, field exams, or "
        "governance. Type 'exit' to return to the menu.",
        title="[bold]ABL Wiki Agent[/bold]", border_style="magenta",
    ))
    while True:
        question = Prompt.ask("[bold cyan]You[/bold cyan]")
        if question.strip().lower() in ("exit", "quit", "q"):
            return
        try:
            result = agent.run(question, on_tool_call=_on_tool_call)
        except RuntimeError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            return
        console.print(Panel(result.text.strip(), title="[bold magenta]ABL Wiki Agent[/bold magenta]", border_style="magenta"))
        if result.citations:
            cites = "; ".join(f"{c['source']} > {c['title']}" for c in result.citations)
            console.print(f"[dim]Sources: {cites}[/dim]\n")
        else:
            console.print("[dim]No knowledge base passages were retrieved for this answer.[/dim]\n")


def process_pending_bbc(deal_id: str) -> None:
    submission = deal_store.get_pending_bbc_submission(deal_id)
    if not submission:
        console.print("[yellow]No pending Borrowing Base Certificate submission on file for this deal.[/yellow]")
        return

    console.print(Panel(submission.get("scenario_note", ""), title="[bold]New BBC submission[/bold]", border_style="blue"))
    workflow = DealWorkflow(deal_id)
    try:
        result, _ = workflow.run_stage("borrowing_base", _approve_change_interactive, on_tool_call=_on_tool_call)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        return
    _print_agent_result(registry.get_agent("borrowing_base").name, registry.get_stage_label("borrowing_base"), result)

    calc = next((tc["result"] for tc in reversed(result.tool_calls) if tc["name"] == "calculate_borrowing_base"), None)
    if not calc:
        console.print("[yellow]The agent did not run the borrowing base calculation, so there is nothing to commit.[/yellow]")
        return

    if Confirm.ask("Commit this certificate to the deal's official BBC history?", default=True):
        entry = {
            "period_end": submission["period_end"],
            "gross_ar": calc["gross_ar"],
            "eligible_ar": calc["eligible_ar"],
            "ar_availability": calc["ar_availability"],
            "inventory_at_cost": calc["inventory_at_cost"],
            "eligible_inventory_at_cost": calc["eligible_inventory_at_cost"],
            "inventory_availability": calc["inventory_availability"],
            "dilution_pct": calc["dilution_pct"],
            "dilution_reserve": calc["dilution_reserve"],
            "rent_reserve": calc["rent_reserve"],
            "borrowing_base": calc["borrowing_base"],
            "outstanding_balance": calc["outstanding_balance"],
            "letters_of_credit": calc["letters_of_credit"],
            "availability": calc["availability"],
            "cash_dominion_active": calc["springing_trigger_breached"],
            "fccr_tested": calc["springing_trigger_breached"],
        }
        deal_store.commit_bbc_submission(deal_id, entry)
        audit_log.append_entry(
            event_type="bbc_committed", deal_id=deal_id, stage="06 - Servicing & Collateral Monitoring",
            actor="human_reviewer", summary=f"Committed BBC for period {submission['period_end']}", detail=entry,
        )
        console.print("[green]Committed.[/green]")

    if calc.get("requested_draw"):
        fundable = calc["draw_fundable_in_full"]
        max_draw = calc["max_fundable_draw"]
        requested = calc["requested_draw"]
        console.print(
            f"\n[bold]Requested incremental draw:[/bold] ${requested:,.0f}  "
            f"({'fundable in full' if fundable else f'only ${max_draw:,.0f} is fundable within the borrowing base'})"
        )
        fund_amount = requested if fundable else max_draw
        if fund_amount > 0 and Confirm.ask(f"Fund ${fund_amount:,.0f} against this deal now?", default=fundable):
            deal = deal_store.get_deal(deal_id)
            new_balance = deal["outstanding_balance"] + fund_amount
            applied = deal_store.apply_change(deal_id, "outstanding_balance", new_balance)
            audit_log.append_entry(
                event_type="draw_funded", deal_id=deal_id, stage="06 - Servicing & Collateral Monitoring",
                actor="human_reviewer", summary=f"Funded ${fund_amount:,.0f} draw", detail=applied,
            )
            console.print(f"[green]Funded ${fund_amount:,.0f}. New outstanding balance: ${new_balance:,.0f}.[/green]")


def view_audit_log() -> None:
    entries = audit_log.read_all()
    if not entries:
        console.print("[yellow]Audit log is empty.[/yellow]")
        return
    table = Table(title="Audit Log")
    table.add_column("Time (UTC)", style="dim")
    table.add_column("Event")
    table.add_column("Stage")
    table.add_column("Actor")
    table.add_column("Summary")
    for e in entries[-40:]:
        table.add_row(e["ts"][:19], e["event_type"], e["stage"] or "-", e["actor"], (e["summary"] or "")[:70])
    console.print(table)

    valid, break_index = audit_log.verify_chain()
    if valid:
        console.print(f"[green]Hash chain verified intact across {len(entries)} entries.[/green]")
    else:
        console.print(f"[bold red]Hash chain BROKEN at entry index {break_index}. Log integrity compromised.[/bold red]")


def rebuild_knowledge_base() -> None:
    count = knowledge_base.ingest(rebuild=True)
    console.print(f"[green]Indexed {count} knowledge base chunks into ChromaDB at {config.CHROMA_DIR}.[/green]")


def main() -> None:
    console.print(Panel(
        "[bold]Agentic ABL Lifecycle Demo[/bold]\n"
        "Multi-agent system covering origination through monitoring, plus the ABL Wiki agent, "
        "backed by ChromaDB retrieval and a hash-chained audit log.",
        border_style="cyan",
    ))

    if not config.ANTHROPIC_API_KEY:
        console.print(
            "[yellow]ANTHROPIC_API_KEY is not set. The Wiki agent and lifecycle-stage agents will not run "
            "until it is configured (see .env.example). The audit log and knowledge-base rebuild options "
            "still work without it.[/yellow]\n"
        )

    deal_id = _select_deal_id()
    _print_deal_snapshot(deal_id)

    menu = {
        "1": ("Run full ABL lifecycle demo (all stages)", lambda: run_full_lifecycle(deal_id)),
        "2": ("Run a single lifecycle stage", lambda: run_single_stage(deal_id)),
        "3": ("Chat with the ABL Wiki agent", chat_with_wiki_agent),
        "4": ("Process the pending Borrowing Base Certificate", lambda: process_pending_bbc(deal_id)),
        "5": ("View audit log", view_audit_log),
        "6": ("Rebuild knowledge base index", rebuild_knowledge_base),
        "0": ("Exit", None),
    }

    while True:
        console.print("\n[bold]Menu[/bold]")
        for key, (label, _) in menu.items():
            console.print(f"  {key}. {label}")
        choice = Prompt.ask("Choose", choices=list(menu.keys()), default="1")
        if choice == "0":
            console.print("Goodbye.")
            return
        menu[choice][1]()


if __name__ == "__main__":
    main()
