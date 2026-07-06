from __future__ import annotations

import asyncio
import logging
import time
from fastapi import BackgroundTasks
from typing import Any, Dict

from app.services.coder import generate_code, apply_file_changes
from app.services.debugger import debug_code, apply_debug_changes
from app.services.reviewer import review_code
from app.services.planner import analyze_requirements, create_plan
from app.services.git_manager import create_checkpoint, rollback_to_checkpoint, ensure_git_repo
from app.services.tester import run_project_tests
from app.services.project_runner import full_validation, estimate_project_eta
from app.services.task_manager import (
    get_task,
    list_pending_tasks,
    update_task_status,
    update_task_progress,
)

# New specialized agent/service imports
from app.services.architect import generate_architecture
from app.services.repository_analyzer import analyze_repository_structure
from app.services.documentation import generate_project_documentation
from app.services.security import audit_code_changes
from app.services.test_engine import generate_unit_tests
from app.services.workspace import WorkspaceManager
from app.services.rag import RetrievalAugmentedGenerator

logger = logging.getLogger("avatar.orchestrator")

POLL_INTERVAL_SECONDS = 3
MAX_DEBUG_RETRIES = 8  # More retries for deep debugging

async def check_control_state(project_id: str, task_id: int) -> bool:
    """Check task control state in DB. Sleeps if task is paused.
    Returns True if the task has been canceled/failed, False if we should continue.
    """
    while True:
        task = get_task(project_id, task_id)
        if not task:
            return True
        if task["status"] in {"failed", "completed"}:
            return True
        if task.get("paused"):
            logger.info("Task %s is paused – waiting...", task_id)
            await asyncio.sleep(1.0)
            continue
        return False

class OrchestrationTask:
    def __init__(
        self,
        task_id: str,
        title: str,
        dependencies: list[str] = None,
        required_files: list[str] = None,
        required_models: list[str] = None,
        expected_output: str = "",
        verification_method: str = "",
        priority: int = 2,
        estimated_cost: float = 0.0,
        estimated_time: float = 0.0,
        parent_task: str | None = None
    ):
        self.id = task_id
        self.title = title
        self.dependencies = dependencies or []
        self.required_files = required_files or []
        self.required_models = required_models or []
        self.expected_output = expected_output
        self.verification_method = verification_method
        self.priority = priority
        self.estimated_cost = estimated_cost
        self.estimated_time = estimated_time
        self.parent_task = parent_task
        self.status = "pending"  # pending, in_progress, completed, failed

class TaskGraph:
    def __init__(self):
        self.tasks: dict[str, OrchestrationTask] = {}

    def add_task(self, task: OrchestrationTask) -> None:
        self.tasks[task.id] = task

    def is_acyclic(self) -> bool:
        visited = {}
        def visit(node_id):
            if visited.get(node_id) == "visiting":
                return False
            if visited.get(node_id) == "visited":
                return True
            visited[node_id] = "visiting"
            for dep in self.tasks[node_id].dependencies:
                if dep in self.tasks:
                    if not visit(dep):
                        return False
            visited[node_id] = "visited"
            return True
        for t_id in self.tasks:
            if not visit(t_id):
                return False
        return True

    def get_ready_tasks(self) -> list[OrchestrationTask]:
        ready = []
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            deps_ok = True
            for dep in task.dependencies:
                dep_task = self.tasks.get(dep)
                if not dep_task or dep_task.status != "completed":
                    deps_ok = False
                    break
            if deps_ok:
                ready.append(task)
        return ready

    def to_subtasks_list(self) -> list[dict]:
        return [
            {
                "id": t.id,
                "title": t.title,
                "status": t.status
            }
            for t in self.tasks.values()
        ]

async def _process_task(task: Dict[str, Any]) -> None:
    project_id = task["payload"].get("project_id") if task.get("payload") else None
    if project_id is None:
        logger.error("Task %s missing project_id – skipping", task["id"])
        update_task_status("", task["id"], "failed")
        return

    from app.main import BASE_DIR
    project_path = (BASE_DIR / project_id).resolve()
    ensure_git_repo(project_path)

    name = task["name"]
    logger.info("Processing task %s (%s) for project %s", task["id"], name, project_id)
    update_task_progress(project_id, task["id"], status="in_progress", progress=5)

    # Initialize Graph Nodes
    graph = TaskGraph()
    graph.add_task(OrchestrationTask("rag", "Retrieve Context & RAG Indexing", priority=1, estimated_time=15))
    graph.add_task(OrchestrationTask("analyzer", "Analyze Repository Structure", priority=1, estimated_time=15))
    graph.add_task(OrchestrationTask("plan", "Analyze Requirements & Generate Plan", dependencies=["rag", "analyzer"], priority=1, estimated_time=20))
    graph.add_task(OrchestrationTask("architecture", "Design System Architecture", dependencies=["plan"], priority=1, estimated_time=30))
    graph.add_task(OrchestrationTask("git_init", "Initialize Git Checkpoint", dependencies=["plan"], priority=1, estimated_time=10))
    graph.add_task(OrchestrationTask("codegen", "Generate Source Code & Apply Patches", dependencies=["architecture", "git_init"], priority=1, estimated_time=60))
    graph.add_task(OrchestrationTask("security", "Perform Security Auditing", dependencies=["codegen"], priority=2, estimated_time=15))
    graph.add_task(OrchestrationTask("review", "Review Code Quality & Conventions", dependencies=["codegen"], priority=2, estimated_time=15))
    graph.add_task(OrchestrationTask("tests_gen", "Generate Target Unit Tests", dependencies=["codegen"], priority=2, estimated_time=20))
    graph.add_task(OrchestrationTask("test", "Execute Build & Verify Tests", dependencies=["security", "review", "tests_gen"], priority=1, estimated_time=30))
    graph.add_task(OrchestrationTask("debug", "Analyze Errors & Auto-Heal Loop", dependencies=["test"], priority=1, estimated_time=60))
    graph.add_task(OrchestrationTask("docs", "Generate Project Documentation", dependencies=["test"], priority=3, estimated_time=20))

    if not graph.is_acyclic():
        raise RuntimeError("Task Graph is not acyclic (contains dependency cycles)")

    update_task_progress(project_id, task["id"], subtasks=graph.to_subtasks_list())

    start_time = time.monotonic()
    project_eta_seconds = 300  # default; updated after planning
    project_eta_str = "~5 minutes"

    # Live timer loop: counts elapsed time and shows remaining ETA
    async def timer_loop():
        while True:
            if await check_control_state(project_id, task["id"]):
                break
            elapsed = time.monotonic() - start_time
            remaining = max(0, project_eta_seconds - int(elapsed))
            if remaining > 3600:
                rem_str = f"~{remaining / 3600:.1f}h remaining"
            elif remaining > 60:
                rem_str = f"~{remaining // 60}m {remaining % 60}s remaining"
            else:
                rem_str = f"~{remaining}s remaining"
            update_task_progress(
                project_id, task["id"],
                elapsed_time=elapsed,
                estimated_remaining_time=rem_str,
                eta=project_eta_str,
            )
            await asyncio.sleep(1.0)

    timer_task = asyncio.create_task(timer_loop())

    # Task execution variables
    context_results = []
    scanned_files = []
    repo_intel = {}
    requirements = {}
    plan = {}
    architecture = {}
    checkpoint_hash = ""
    changes = []
    security_report = {}
    review_report = {}
    test_files = []
    test_success = False
    debug_success = False
    validation_report = {}

    ws = WorkspaceManager(project_id)
    rag = RetrievalAugmentedGenerator(project_path)
    user_input = task["payload"].get("prompt", "Analyze requirements and fix current code bugs")

    async def execute_task_node(task_node: OrchestrationTask) -> None:
        nonlocal context_results, scanned_files, repo_intel, requirements, plan
        nonlocal architecture, checkpoint_hash, changes, security_report, review_report
        nonlocal test_files, test_success, debug_success

        task_node.status = "in_progress"
        update_task_progress(project_id, task["id"], subtasks=graph.to_subtasks_list(), current_agent=task_node.title)
        logger.info("Starting Task Node: %s (%s)", task_node.id, task_node.title)

        try:
            if task_node.id == "rag":
                context_results = await rag.retrieve_context(user_input, limit=5)
                task_node.status = "completed"

            elif task_node.id == "analyzer":
                scanned_files = ws.list_files()
                repo_intel = await analyze_repository_structure(project_id, scanned_files)
                task_node.status = "completed"

            elif task_node.id == "plan":
                requirements = await analyze_requirements(project_id, user_input)
                plan = await create_plan(project_id, requirements)

                # Calculate and broadcast ETA immediately after planning
                nonlocal project_eta_seconds, project_eta_str
                project_eta_seconds, project_eta_str = estimate_project_eta(plan)
                file_count = len(plan.get("files", []))
                logger.info("Project ETA: %s (%d files planned)", project_eta_str, file_count)
                update_task_progress(
                    project_id, task["id"],
                    eta=project_eta_str,
                    log=f"Plan complete: {file_count} files to generate. Estimated time: {project_eta_str}",
                )
                task_node.status = "completed"

            elif task_node.id == "architecture":
                architecture = await generate_architecture(project_id, plan)
                task_node.status = "completed"

            elif task_node.id == "git_init":
                checkpoint_hash = create_checkpoint(project_path, f"Before active coding task {task['id']}")
                task_node.status = "completed"

            elif task_node.id == "codegen":
                coder_result = await generate_code(project_id, plan)
                if coder_result.get("error"):
                    raise RuntimeError(coder_result["error"])
                changes = coder_result.get("file_changes", [])
                modified = await apply_file_changes(project_id, changes)
                logger.info("Coder applied %d files: %s", len(modified), modified)

                # Write ARCHITECTURE.md so it always appears in the workspace tree
                arch_lines = [
                    f"# {project_id.title()} – Architecture Overview\n",
                    "\n**Generated by Avatar Autonomous Engineering Pipeline**\n\n",
                ]
                if architecture:
                    if arch_summary := architecture.get("architecture_summary"):
                        arch_lines.append(f"## Summary\n{arch_summary}\n\n")
                    if interfaces := architecture.get("interfaces"):
                        arch_lines.append("## Interfaces\n")
                        for iface in interfaces:
                            arch_lines.append(f"- **{iface.get('name')}** ({iface.get('type', '')}): {iface.get('description', '')}\n")
                        arch_lines.append("\n")
                    if data_models := architecture.get("data_models"):
                        arch_lines.append("## Data Models\n")
                        for dm in data_models:
                            fields = dm.get('fields', [])
                            arch_lines.append(f"- **{dm.get('name')}**: {', '.join(str(f) for f in fields)}\n")
                        arch_lines.append("\n")
                arch_lines.append(f"## Generated Files ({len(modified)} total)\n")
                for m in modified:
                    arch_lines.append(f"- `{m}`\n")
                arch_lines.append(f"\n---\n*ETA: {project_eta_str}*\n")
                ws.write_file("ARCHITECTURE.md", "".join(arch_lines))
                task_node.status = "completed"

            elif task_node.id == "security":
                security_report = await audit_code_changes(project_id, changes)
                task_node.status = "completed"

            elif task_node.id == "review":
                review_report = await review_code(project_id, changes)
                task_node.status = "completed"

            elif task_node.id == "tests_gen":
                test_changes = await generate_unit_tests(project_id, changes, plan)
                if test_files_list := test_changes.get("test_changes"):
                    await apply_file_changes(project_id, test_files_list)
                task_node.status = "completed"

            elif task_node.id == "test":
                # Step 1: Full project validation (syntax + deps + entry-point run)
                nonlocal validation_report
                validation_report = await full_validation(project_path)
                logger.info("Validation: success=%s errors=%s",
                            validation_report["success"], validation_report.get("errors", []))

                # Step 2: Run test suite
                test_result = await run_project_tests(project_path)
                logger.info("Tests: success=%s passed=%d failed=%d",
                            test_result["success"], test_result["passed"], test_result["failed"])

                test_success = validation_report["success"] and test_result["success"]
                task_node.status = "completed"
                if test_success:
                    graph.tasks["debug"].status = "completed"

            elif task_node.id == "debug":
                if test_success:
                    task_node.status = "completed"
                    return

                retry_count = 0
                while retry_count < MAX_DEBUG_RETRIES:
                    if await check_control_state(project_id, task["id"]):
                        return

                    update_task_progress(
                        project_id, task["id"],
                        subtasks=graph.to_subtasks_list(),
                        current_agent=f"Debugger (attempt {retry_count + 1}/{MAX_DEBUG_RETRIES})",
                    )

                    # Re-validate the project after previous fix
                    validation_report = await full_validation(project_path)
                    test_result = await run_project_tests(project_path)

                    if validation_report["success"] and test_result["success"]:
                        debug_success = True
                        logger.info("Auto-heal succeeded on attempt %d", retry_count + 1)
                        break

                    logger.warning("Auto-heal retry %d/%d", retry_count + 1, MAX_DEBUG_RETRIES)

                    # Build rich error context – include actual file contents of failing files
                    all_errors = (
                        validation_report.get("errors", []) +
                        [test_result.get("stderr", ""), test_result.get("stdout", "")]
                    )
                    error_text = "\n".join(str(e) for e in all_errors if e)

                    # Read source files for debugger context
                    file_contexts = {}
                    syntax_errors = []
                    for step in validation_report.get("steps", []):
                        if step.get("name") == "syntax_check":
                            syntax_errors = step.get("syntax_errors", [])

                    for se in syntax_errors:
                        fp = project_path / se["file"]
                        try:
                            file_contexts[se["file"]] = fp.read_text(encoding="utf-8")[:3000]
                        except Exception:
                            pass

                    # Also grab the entry-point file
                    for candidate in ["main.py", "app.py", "server.py", "index.js"]:
                        fp = project_path / candidate
                        if fp.exists() and candidate not in file_contexts:
                            try:
                                file_contexts[candidate] = fp.read_text(encoding="utf-8")[:3000]
                            except Exception:
                                pass

                    error_payload = {
                        "error": error_text[:4000],
                        "logs": test_result.get("stdout", "")[:2000],
                        "test_failures": test_result.get("failed", 0),
                        "file_contexts": file_contexts,
                        "retry": retry_count + 1,
                    }

                    debugger_result = await debug_code(project_id, error_payload)
                    if debugger_result.get("error"):
                        logger.error("Debugger error: %s", debugger_result["error"])
                    else:
                        dbg_changes = debugger_result.get("file_changes", [])
                        if dbg_changes:
                            await apply_debug_changes(project_id, dbg_changes)
                            logger.info("Applied %d debug fixes", len(dbg_changes))

                    retry_count += 1

                if debug_success or test_success:
                    task_node.status = "completed"
                else:
                    task_node.status = "failed"
                    if checkpoint_hash:
                        rollback_to_checkpoint(project_path, checkpoint_hash)
                    raise RuntimeError(
                        f"Project failed validation after {MAX_DEBUG_RETRIES} debug attempts. "
                        f"Errors: {'; '.join(validation_report.get('errors', []))[:500]}"
                    )

            elif task_node.id == "docs":
                docs_changes = await generate_project_documentation(project_id, changes, plan)
                if docs_files_list := docs_changes.get("documentation_changes"):
                    await apply_file_changes(project_id, docs_files_list)
                task_node.status = "completed"

        except Exception as e:
            logger.exception("Task Node %s execution error: %s", task_node.id, e)
            task_node.status = "failed"
        finally:
            total_nodes = len(graph.tasks)
            completed_nodes = sum(1 for t in graph.tasks.values() if t.status == "completed")
            progress_val = 5 + int((completed_nodes / total_nodes) * 90)
            update_task_progress(
                project_id, task["id"],
                progress=progress_val,
                subtasks=graph.to_subtasks_list()
            )

        logger.info("Finished Task Node: %s (status=%s)", task_node.id, task_node.status)

    try:
        if name in {"code_generation", "debug"}:
            while True:
                if await check_control_state(project_id, task["id"]): return
                
                ready_tasks = graph.get_ready_tasks()
                active_tasks = [t for t in graph.tasks.values() if t.status == "in_progress"]
                
                if not ready_tasks and not active_tasks:
                    # Check if any tasks failed
                    failed_tasks = [t for t in graph.tasks.values() if t.status == "failed"]
                    if failed_tasks:
                        raise RuntimeError(f"Task Graph execution failed at tasks: {[t.id for t in failed_tasks]}")
                    
                    pending_tasks = [t for t in graph.tasks.values() if t.status == "pending"]
                    if pending_tasks:
                        raise RuntimeError(f"Deadlock in task graph. Pending: {[t.id for t in pending_tasks]}")
                    
                    break
                
                if ready_tasks:
                    logger.info("Concurrently scheduling tasks: %s", [t.id for t in ready_tasks])
                    await asyncio.gather(*(execute_task_node(t) for t in ready_tasks))
                else:
                    await asyncio.sleep(0.5)

            # Create final success checkpoint commit
            create_checkpoint(project_path, f"Task completed successfully: {task['id']}")
            
            update_task_progress(project_id, task["id"], progress=100, current_agent="Memory Manager")
            update_task_status(project_id, task["id"], "completed")

        else:
            logger.warning("Unknown task type %s – marking as completed", name)
            update_task_status(project_id, task["id"], "completed")

    except Exception as exc:
        logger.exception("Task %s failed: %s", task["id"], exc)
        update_task_status(project_id, task["id"], "failed")
    finally:
        timer_task.cancel()
        try:
            await timer_task
        except asyncio.CancelledError:
            pass


async def orchestrator_loop() -> None:
    """Continuously poll for pending tasks and dispatch them.
    Runs forever in the background. Errors are caught per‑task.
    """
    logger.info("Orchestrator loop started")
    while True:
        try:
            # Poll the default workspace tasks (project_id="")
            from app.main import BASE_DIR
            ensure_git_repo(BASE_DIR)
            
            pending_default = list_pending_tasks("")
            for task in pending_default:
                await _process_task(task)

            # Poll other project subdirectories
            for project_dir in BASE_DIR.iterdir():
                if not project_dir.is_dir() or project_dir.name == ".git":
                    continue
                project_id = project_dir.name
                pending = list_pending_tasks(project_id)
                for task in pending:
                    await _process_task(task)
        except Exception as e:
            logger.exception("Orchestrator loop encountered an error: %s", e)
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

def start_background_tasks(background_tasks: BackgroundTasks) -> None:
    """FastAPI hook to start the orchestrator loop as a background task.
    Called from the app startup event.
    """
    background_tasks.add_task(orchestrator_loop)
