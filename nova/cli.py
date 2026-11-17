"""N.O.V.A. Command Line Interface and System Dashboard."""

import argparse
import sys

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

from nova.core.orchestrator import AgentOrchestrator
from nova.grounding.hybrid_grounder import HybridGroundingEngine
from nova.security.interceptor import SecurityInterceptor
from nova.sensory.tts import StreamingTTS
from nova.sensory.stt import StreamingSTT
from nova.memory.lancedb_store import LocalMemoryStore


def print_banner():
    if HAS_RICH:
        banner = Text()
        banner.append("✦ N.O.V.A. ", style="bold cyan")
        banner.append("(Native Operating Vector Assistant)\n", style="bold white")
        banner.append("Privacy-First, Cross-Platform Autonomous OS Agent Runtime", style="dim italic")
        console.print(Panel(banner, border_style="cyan"))
    else:
        print("================================================================")
        print("✦ N.O.V.A. (Native Operating Vector Assistant)")
        print("Privacy-First, Cross-Platform Autonomous OS Agent Runtime")
        print("================================================================")


def cmd_status(args):
    print_banner()
    grounding = HybridGroundingEngine()
    active_win = grounding.get_active_window()
    windows = grounding.list_windows()

    from nova.core.ai_engine import LocalAIEngine
    from nova.memory.habit_learner import HabitMemoryEngine

    ai = LocalAIEngine()
    habits = HabitMemoryEngine()

    props = [
        ("Operating System", grounding.os_type.value.upper()),
        ("Accessibility Backend", type(grounding.driver).__name__),
        ("A11y Permissions Active", str(grounding.driver.is_available())),
        ("Local AI Brain (LLaMA)", f"{ai.active_backend or 'Offline / Reflex Router'} ({ai.active_model or 'None'})"),
        ("Learned User Habits", f"{len(habits.recent_interactions)} interactions recorded"),
        ("Active Foreground Window", active_win.title if active_win else "None"),
        ("Active Application", active_win.app_name if active_win else "None"),
        ("Total Visible Windows", str(len(windows))),
        ("Local Vector Engine", "LanceDB (Embedded)"),
        ("Speech Recognition", "faster-whisper (Offline base.en)"),
    ]

    if HAS_RICH:
        table = Table(title="System & Runtime Environment", show_header=True, header_style="bold magenta")
        table.add_column("Property", style="dim")
        table.add_column("Value", style="bold green")
        for k, v in props:
            table.add_row(k, v)
        console.print(table)
    else:
        print("\n--- System & Runtime Environment ---")
        for k, v in props:
            print(f"  {k:<26}: {v}")
        print()


def cmd_inspect(args):
    print_banner()
    grounding = HybridGroundingEngine()
    active_win = grounding.get_active_window()
    if not active_win:
        msg = "No active window detected."
        if HAS_RICH:
            console.print(f"[red]{msg}[/red]")
        else:
            print(f"ERROR: {msg}")
        return

    tree = grounding.inspect_ui(active_win)
    interactive_items = tree.flatten_interactive()

    if HAS_RICH:
        console.print(f"[bold cyan]Inspecting Active Window:[/bold cyan] {active_win.title} ({active_win.app_name})")
        table = Table(title=f"Extracted UI Nodes ({len(interactive_items)} interactive controls)", show_header=True)
        table.add_column("Node ID", style="dim")
        table.add_column("Role", style="yellow")
        table.add_column("Name / Label", style="bold white")
        table.add_column("Center (X, Y)", style="green")
        table.add_column("Secure", style="red")

        for item in interactive_items[:25]:
            cx, cy = item.bounding_box.center
            table.add_row(
                item.id,
                item.role.value,
                item.name or "<unnamed>",
                f"({int(cx)}, {int(cy)})",
                "YES" if item.is_secure else "no",
            )
        console.print(table)
    else:
        print(f"\nInspecting Active Window: {active_win.title} ({active_win.app_name})")
        print(f"Interactive Controls Found: {len(interactive_items)}")
        for item in interactive_items[:25]:
            cx, cy = item.bounding_box.center
            print(f"  - [{item.role.value:<12}] {item.name or '<unnamed>'} at ({int(cx)}, {int(cy)}) (ID: {item.id})")
        print()


def cmd_run(args):
    print_banner()
    grounding = HybridGroundingEngine()
    security = SecurityInterceptor()
    tts = StreamingTTS()
    memory = LocalMemoryStore()

    orchestrator = AgentOrchestrator(
        grounding=grounding,
        security=security,
        tts=tts,
        memory=memory,
    )

    if HAS_RICH:
        console.print(f"[bold yellow]Executing Intent:[/bold yellow] [italic]'{args.intent}'[/italic]\n")
    else:
        print(f"\nExecuting Intent: '{args.intent}'\n")

    def on_step(plan, result):
        if HAS_RICH:
            console.print(f"[cyan]Step {plan.step_id}:[/cyan] {plan.thought}")
            console.print(f"  Action: [bold]{plan.action_type.value}[/bold] -> [dim]{result.output_message}[/dim] ({result.latency_ms:.1f}ms)\n")
        else:
            print(f"Step {plan.step_id}: {plan.thought}")
            print(f"  Action: {plan.action_type.value} -> {result.output_message} ({result.latency_ms:.1f}ms)\n")

    results = orchestrator.execute_user_intent(args.intent, on_step_update=on_step)
    if HAS_RICH:
        console.print(f"[bold green]Execution completed ({len(results)} steps).[/bold green]")
    else:
        print(f"Execution completed ({len(results)} steps).")


def cmd_listen(args):
    print_banner()
    from nova.sensory.listener import VoiceDaemon

    grounding = HybridGroundingEngine()
    security = SecurityInterceptor()
    tts = StreamingTTS()
    memory = LocalMemoryStore()

    orchestrator = AgentOrchestrator(
        grounding=grounding,
        security=security,
        tts=tts,
        memory=memory,
    )

    daemon = VoiceDaemon(orchestrator=orchestrator)
    try:
        daemon.start_listening()
    except KeyboardInterrupt:
        print("\nVoice listener stopped.")


def cmd_habits(args):
    print_banner()
    from nova.memory.habit_learner import HabitMemoryEngine
    habits = HabitMemoryEngine()

    if HAS_RICH:
        console.print(Panel("[bold magenta]📊 N.O.V.A. Continuous Habit & Preference Profile[/bold magenta]", border_style="magenta"))
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Category", style="dim")
        table.add_column("Learned Preferences & Frequency", style="white")

        # Top Contacts
        contacts_str = ", ".join([f"{c} ({cnt}x)" for c, cnt in sorted(habits.habits.get("contacts", {}).get("whatsapp", {}).items(), key=lambda x: x[1], reverse=True)[:5]]) or "None yet"
        table.add_row("WhatsApp Contacts", contacts_str)

        # Top Apps
        apps_str = ", ".join([f"{a} ({cnt}x)" for a, cnt in sorted(habits.habits.get("apps", {}).items(), key=lambda x: x[1], reverse=True)[:5]]) or "None yet"
        table.add_row("Frequent Apps", apps_str)

        # Top Websites
        sites_str = ", ".join([f"{s} ({cnt}x)" for s, cnt in sorted(habits.habits.get("websites", {}).items(), key=lambda x: x[1], reverse=True)[:5]]) or "None yet"
        table.add_row("Favorite Sites", sites_str)

        # Custom Aliases
        aliases_str = ", ".join([f"'{k}' -> {v}" for k, v in habits.habits.get("custom_aliases", {}).items()])
        table.add_row("Custom Aliases", aliases_str)

        table.add_row("Total Interactions", f"{len(habits.recent_interactions)} recorded")
        console.print(table)
    else:
        print("\n--- Learned User Habits & Profile ---")
        print(f"  Contacts: {habits.habits.get('contacts', {})}")
        print(f"  Apps: {habits.habits.get('apps', {})}")
        print(f"  Websites: {habits.habits.get('websites', {})}")
        print(f"  Total Interactions: {len(habits.recent_interactions)}")


def cmd_ai(args):
    print_banner()
    from nova.core.ai_engine import LocalAIEngine
    ai = LocalAIEngine()

    if HAS_RICH:
        console.print(Panel("[bold purple]🧠 N.O.V.A. Local Open-Source AI Brain (LLaMA / Ollama)[/bold purple]", border_style="purple"))

        if ai.is_available:
            console.print(f"[bold green]● Local AI Connected![/bold green]")
            console.print(f"  Backend: [cyan]{ai.active_backend}[/cyan]")
            console.print(f"  Model:   [bold white]{ai.active_model}[/bold white]")
            console.print(f"  URL:     [dim]{ai.base_url}[/dim]\n")

            test_query = "yo ping frosty saying I will be 10 minutes late on whatsapp"
            console.print(f"[dim]Testing Neural Understanding on: '{test_query}'...[/dim]")
            res = ai.reason_and_plan(test_query)
            if res:
                thought, actions = res
                console.print(f"  [green]Thought:[/green] {thought}")
                for a in actions:
                    console.print(f"  [cyan]Plan:[/cyan] {a.parameters.get('skill', a.action_type.value)} -> {a.parameters}")
        else:
            console.print("[bold yellow]⚠️  No Local LLM Server Detected on standard ports.[/bold yellow]\n")
            console.print("[white]N.O.V.A. is currently using its [bold cyan]Fast Deterministic Reflex Router[/bold cyan].[/white]\n")
            console.print("[bold green]To enable the full cognitive LLaMA AI Brain offline:[/bold green]")
            console.print("  1. Install Ollama: [cyan]brew install ollama[/cyan] or download from [underline]https://ollama.com[/underline]")
            console.print("  2. Run LLaMA 3.2:  [cyan]ollama run llama3.2[/cyan]\n")
            console.print("[dim]Once started, NOVA will automatically detect LLaMA with zero configuration required.[/dim]")
    else:
        print("AI Brain Available:", ai.is_available)
        print("Backend:", ai.active_backend)
        print("Model:", ai.active_model)


def main():
    parser = argparse.ArgumentParser(description="N.O.V.A. Agent Engine")
    subparsers = parser.add_subparsers(dest="command")

    # Status
    subparsers.add_parser("status", help="Displays local OS agent runtime status")

    # Inspect
    subparsers.add_parser("inspect", help="Inspects active window accessibility tree")

    # Listen (Hands-free voice daemon)
    subparsers.add_parser("listen", help="Runs continuous hands-free voice listener")

    # Habits
    subparsers.add_parser("habits", help="Displays learned user habits, frequent contacts, and preferences")

    # AI Brain
    subparsers.add_parser("ai", help="Tests local LLM (LLaMA / Ollama) connectivity and models")

    # Run
    run_parser = subparsers.add_parser("run", help="Executes a natural language desktop command")
    run_parser.add_argument("intent", type=str, help="User intent or goal")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "status":
        cmd_status(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "listen":
        cmd_listen(args)
    elif args.command == "habits":
        cmd_habits(args)
    elif args.command == "ai":
        cmd_ai(args)
    elif args.command == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()
