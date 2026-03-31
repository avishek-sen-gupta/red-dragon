"""Survey all Java files in legacy-app sample and attempt to run LegacyDBQueryTest.

Usage:
    poetry run python experiments/legacy_ir_export/survey_and_run.py
"""

import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from interpreter.cfg import build_cfg
from interpreter.constants import Language
from interpreter.frontend import get_frontend
from interpreter.instructions import InstructionBase
from interpreter.ir import CodeLabel, Opcode
from interpreter.project.compiler import compile_module, build_export_table
from interpreter.project.imports import extract_imports
from interpreter.project.linker import link_modules
from interpreter.project.types import ModuleUnit
from interpreter.registry import build_registry
from interpreter.run import build_execution_strategies, execute_cfg
from interpreter.run_types import VMConfig, UnresolvedCallStrategy

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

legacy-app_ROOT = Path("/Users/asgupta/code/legacy-app/legacy_sample")
OUTPUT_DIR = Path("experiments/legacy_ir_export/output")

# ── Phase 1: Survey ────────────────────────────────────────────────


def survey_all_java_files() -> dict:
    """Lower every .java file and collect stats."""
    java_files = sorted(legacy-app_ROOT.rglob("*.java"))
    logger.info("Found %d Java files", len(java_files))

    results = []
    total_instructions = 0
    total_functions = 0
    total_classes = 0
    errors = []
    opcode_counts: Counter = Counter()
    module_to_exports: dict[str, dict] = {}

    frontend = get_frontend(Language.JAVA)

    for i, f in enumerate(java_files):
        rel = f.relative_to(legacy-app_ROOT)
        try:
            source = f.read_bytes()
            t0 = time.perf_counter()

            # Re-create frontend for each file to reset state
            frontend = get_frontend(Language.JAVA)
            ir = frontend.lower(source)
            elapsed = time.perf_counter() - t0

            # Count opcodes
            for inst in ir:
                opcode_counts[inst.opcode.value] += 1

            # Extract exports
            exports = build_export_table(
                ir, frontend.func_symbol_table, frontend.class_symbol_table
            )

            # Extract imports
            imports = extract_imports(source, f, Language.JAVA)
            import_modules = [ref.module_path for ref in imports]

            n_funcs = len(exports.functions)
            n_classes = len(exports.classes)
            total_instructions += len(ir)
            total_functions += n_funcs
            total_classes += n_classes

            entry = {
                "file": str(rel),
                "lines": source.count(b"\n") + 1,
                "instructions": len(ir),
                "functions": n_funcs,
                "classes": n_classes,
                "imports": import_modules,
                "exported_funcs": [str(k) for k in exports.functions.keys()],
                "exported_classes": [str(k) for k in exports.classes.keys()],
                "time_ms": round(elapsed * 1000, 1),
            }
            results.append(entry)

            module_to_exports[str(rel)] = {
                "functions": {str(k): str(v) for k, v in exports.functions.items()},
                "classes": {str(k): str(v) for k, v in exports.classes.items()},
            }

            if (i + 1) % 50 == 0:
                logger.info("  Surveyed %d/%d files...", i + 1, len(java_files))

        except Exception as e:
            errors.append({"file": str(rel), "error": str(e)})
            results.append({"file": str(rel), "error": str(e)})

    survey = {
        "total_files": len(java_files),
        "successful": len(java_files) - len(errors),
        "errors": len(errors),
        "total_instructions": total_instructions,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "opcode_distribution": dict(opcode_counts.most_common()),
        "error_details": errors[:20],
        "files": results,
    }

    return survey


# ── Phase 2: Multi-file compilation ─────────────────────────────────


def compile_all_and_link(entry_file: Path) -> dict:
    """Compile all Java files in legacy-app and link them together.

    Since the Java resolver can't handle multi-module Maven projects,
    we manually compile all files and build a synthetic import graph.
    """
    java_files = sorted(legacy-app_ROOT.rglob("*.java"))
    logger.info("Compiling %d files for linking...", len(java_files))

    modules: dict[Path, ModuleUnit] = {}
    compile_errors: list[dict] = []

    for f in java_files:
        try:
            mod = compile_module(f, Language.JAVA)
            modules[f.resolve()] = mod
        except Exception as e:
            compile_errors.append(
                {"file": str(f.relative_to(legacy-app_ROOT)), "error": str(e)}
            )

    logger.info(
        "  Compiled %d/%d modules (%d errors)",
        len(modules),
        len(java_files),
        len(compile_errors),
    )

    # Build import graph: map each module's imports to resolved module paths
    # Since Java uses package paths, we build a lookup: package.Class → Path
    package_to_path: dict[str, Path] = {}
    for path, mod in modules.items():
        for cls_name in mod.exports.classes:
            # Infer package from file path relative to source root
            # e.g., Legacy_sample/src/main/java/sg/gov/agency/legacy/LegacyDBQueryTest.java
            # → sg.gov.agency.legacy.LegacyDBQueryTest
            rel = path.relative_to(legacy-app_ROOT)
            parts = list(rel.parts)

            # Strip Maven source root prefixes
            for prefix in [
                ["Legacy_sample", "src", "main", "java"],
                ["Legacy_sample", "Legacy_sample", "src", "main", "java"],
                ["vendor_framework_sample", "src", "main", "java"],
                ["vendor_framework_stubs", "src", "main", "java"],
                ["base_module", "src", "main", "java"],
                ["commons_module", "src", "main", "java"],
                ["newLegacy_sample", "src", "main", "java"],
            ]:
                if parts[: len(prefix)] == prefix:
                    parts = parts[len(prefix) :]
                    break

            # Build fully qualified name
            fqn = ".".join(parts).replace(".java", "")
            package_to_path[fqn] = path

            # Also register by simple class name
            simple = str(cls_name)
            if simple not in package_to_path:
                package_to_path[simple] = path

    logger.info("  Registered %d package→path mappings", len(package_to_path))

    # Build import graph
    import_graph: dict[Path, list[Path]] = {p: [] for p in modules}
    for path, mod in modules.items():
        for imp in mod.imports:
            # Try to resolve by module_path (e.g., com.vendorsoftware.support)
            # For wildcard imports, try to find any file in that package
            if imp.names == ("*",):
                # Find all files whose package matches
                pkg = imp.module_path
                for fqn, target in package_to_path.items():
                    if fqn.startswith(pkg) and target != path:
                        if target not in import_graph[path]:
                            import_graph[path].append(target)
            else:
                for name in imp.names:
                    fqn = f"{imp.module_path}.{name}" if imp.module_path else name
                    if fqn in package_to_path:
                        target = package_to_path[fqn]
                        if target != path and target not in import_graph[path]:
                            import_graph[path].append(target)

    resolved_imports = sum(len(v) for v in import_graph.values())
    logger.info("  Resolved %d import edges", resolved_imports)

    # Now try to link — but linker expects topological sort
    # For now, just merge all IR and try to run the entry point
    entry = entry_file.resolve()
    if entry not in modules:
        return {"error": f"Entry file {entry} not compiled"}

    # Merge all IR from all modules
    all_ir: list[InstructionBase] = []
    for mod in modules.values():
        all_ir.extend(mod.ir)

    logger.info(
        "  Merged IR: %d total instructions from %d modules", len(all_ir), len(modules)
    )

    return {
        "modules_compiled": len(modules),
        "compile_errors": len(compile_errors),
        "error_details": compile_errors[:10],
        "package_mappings": len(package_to_path),
        "import_edges": resolved_imports,
        "merged_instructions": len(all_ir),
        "all_ir": all_ir,
        "modules": modules,
        "entry": entry,
    }


# ── Phase 3: Execute ────────────────────────────────────────────────


def try_execute(all_ir: list[InstructionBase], entry_func: str = "") -> dict:
    """Try to build CFG and execute from the merged IR."""
    logger.info("Building CFG from %d merged instructions...", len(all_ir))
    cfg = build_cfg(all_ir)
    logger.info("  CFG: %d blocks", len(cfg.blocks))

    # Build a frontend just to get empty symbol tables
    frontend = get_frontend(Language.JAVA)
    registry = build_registry(all_ir, cfg)
    logger.info(
        "  Registry: %d functions, %d classes",
        len(registry.func_params),
        len(registry.classes),
    )

    # Find the main function
    main_labels = [label for label in cfg.blocks if "main" in str(label).lower()]
    logger.info("  main-like labels: %s", main_labels[:10])

    if entry_func:
        entry_candidates = [
            label for label in cfg.blocks if entry_func.lower() in str(label).lower()
        ]
        if entry_candidates:
            entry_label = entry_candidates[0]
        else:
            entry_label = (
                CodeLabel(cfg.entry) if isinstance(cfg.entry, str) else cfg.entry
            )
    else:
        entry_label = CodeLabel(cfg.entry) if isinstance(cfg.entry, str) else cfg.entry

    logger.info("  Using entry: %s", entry_label)

    strategies = build_execution_strategies(frontend, all_ir, registry, Language.JAVA)
    vm_config = VMConfig(
        max_steps=2000,
        source_language=Language.JAVA,
        unresolved_call_strategy=UnresolvedCallStrategy.SYMBOLIC,
        verbose=True,
    )

    try:
        vm, exec_stats = execute_cfg(cfg, entry_label, registry, vm_config, strategies)
        return {
            "success": True,
            "steps": exec_stats.steps,
            "llm_calls": exec_stats.llm_calls,
            "heap_objects": exec_stats.final_heap_objects,
            "symbolic_count": exec_stats.final_symbolic_count,
            "call_stack_depth": len(vm.call_stack),
            "vars": {str(k): str(v) for k, v in vm.current_frame.local_vars.items()},
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


# ── Main ────────────────────────────────────────────────────────────


if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: Survey
    logger.info("═══ Phase 1: Survey all Java files ═══")
    survey = survey_all_java_files()

    logger.info("\n═══ Survey Results ═══")
    logger.info(
        "  Files: %d successful, %d errors", survey["successful"], survey["errors"]
    )
    logger.info("  Total IR instructions: %d", survey["total_instructions"])
    logger.info("  Total functions: %d", survey["total_functions"])
    logger.info("  Total classes: %d", survey["total_classes"])
    logger.info(
        "  Top opcodes: %s", dict(list(survey["opcode_distribution"].items())[:10])
    )

    # Save survey
    survey_path = OUTPUT_DIR / "legacy_survey.json"
    # Don't include full file list in the saved output to keep it manageable
    survey_summary = {k: v for k, v in survey.items() if k != "files"}
    survey_summary["files_sample"] = survey["files"][:10]
    survey_path.write_text(json.dumps(survey_summary, indent=2, default=str))
    logger.info("  Saved survey to %s", survey_path)

    # Phase 2: Compile all and link
    logger.info("\n═══ Phase 2: Compile all files for linked execution ═══")
    entry_file = (
        legacy-app_ROOT
        / "Legacy_sample"
        / "src"
        / "main"
        / "java"
        / "sg"
        / "gov"
        / "sla"
        / "stars"
        / "LegacyDBQueryTest.java"
    )
    link_result = compile_all_and_link(entry_file)

    if "error" in link_result and "all_ir" not in link_result:
        logger.error("Linking failed: %s", link_result["error"])
        sys.exit(1)

    logger.info("\n═══ Phase 3: Attempt execution of LegacyDBQueryTest.main() ═══")
    exec_result = try_execute(link_result["all_ir"], entry_func="main")

    logger.info("\n═══ Execution Result ═══")
    for k, v in exec_result.items():
        if k == "vars":
            logger.info("  variables: %d vars in current frame", len(v))
        else:
            logger.info("  %s: %s", k, v)

    # Save results
    result_path = OUTPUT_DIR / "legacy_execution_result.json"
    result_path.write_text(
        json.dumps(
            {
                "survey_summary": {k: v for k, v in survey.items() if k != "files"},
                "link_result": {
                    k: v
                    for k, v in link_result.items()
                    if k not in ("all_ir", "modules")
                },
                "execution": exec_result,
            },
            indent=2,
            default=str,
        )
    )
    logger.info("  Saved results to %s", result_path)
