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

    props = [
        ("Operating System", grounding.os_type.value.upper()),
        ("Accessibility Backend", type(grounding.driver).__name__),
        ("A11y Permissions Active", str(grounding.driver.is_available())),
        ("Active Foreground Window", active_win.title if active_win else "None"),
        ("Active Application", active_win.app_name if active_win else "None"),
        ("Total Visible Windows", str(len(windows))),
        ("Local Vector Engine", "LanceDB (Embedded)"),
        ("Speech Stack", "Streaming VAD + Moonshine + Kokoro-82M"),
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


def main():
    parser = argparse.ArgumentParser(description="N.O.V.A. Agent Engine")
    subparsers = parser.add_subparsers(dest="command")

    # Status
    subparsers.add_parser("status", help="Displays local OS agent runtime status")

    # Inspect
    subparsers.add_parser("inspect", help="Inspects active window accessibility tree")

    # Listen (Hands-free voice daemon)
    subparsers.add_parser("listen", help="Runs continuous hands-free voice listener")

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
    elif args.command == "run":
        cmd_run(args)


if __name__ == "__main__":
    main()
