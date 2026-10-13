"""On Windows, GnuCOBOL 3.2 fails when its own install path contains spaces. verify.py computes the 8.3 short path at runtime and passes it to cobc via environment variables."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from idem.schemas import CaseResult, TestCase, VerificationReport


class VerificationError(RuntimeError):
    """A compiler or runtime could not execute a verification case."""


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VerificationError(f"Command failed: {' '.join(command)}\n{exc}") from exc


def _require_success(stage: str, result: subprocess.CompletedProcess[str]) -> None:
    if result.returncode != 0:
        raise VerificationError(
            f"{stage} failed (exit {result.returncode})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _normalize(output: str) -> str:
    return "\n".join(line.rstrip() for line in output.splitlines()).rstrip("\n")


def _short_path(path: str) -> str:
    if os.name != "nt":
        return path
    try:
        import ctypes

        short_buffer = ctypes.create_unicode_buffer(32768)
        get_short_path = ctypes.windll.kernel32.GetShortPathNameW
        get_short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        if not get_short_path(path, short_buffer, len(short_buffer)) or not short_buffer.value:
            return path
        return short_buffer.value
    except Exception:
        return path


def _compiler_environment() -> dict[str, str]:
    env = os.environ.copy()
    if os.name != "nt":
        return env

    cobc = shutil.which("cobc")
    if not cobc:
        return env
    cobc_dir = Path(cobc).parent
    if cobc_dir.name.casefold() == "bin":
        root = cobc_dir.parent
    elif env.get("COB_MAIN_DIR"):
        root = Path(env["COB_MAIN_DIR"].rstrip("\\/"))
    else:
        return env
    if not root.is_dir():
        return env

    long_root = str(root)
    short_root = _short_path(long_root)

    for name in ("COB_MAIN_DIR", "COB_CC", "COB_CONFIG_DIR", "COB_COPY_DIR", "COB_CFLAGS", "COB_LDFLAGS"):
        if name in env:
            env[name] = env[name].replace(long_root, short_root)
    bundled_lib = Path(short_root) / "lib" / "libcob.a"
    if bundled_lib.exists():
        env["COB_LIBS"] = f"-L {Path(short_root) / 'lib'} -lcob"
    bundled_bins = [Path(short_root) / "bin", Path(short_root) / "mingw64" / "bin"]
    env["PATH"] = os.pathsep.join([*(str(path) for path in bundled_bins), env.get("PATH", "")])
    return env


def _compile(
    cobol_src: str,
    java_src: str,
    root: Path,
    env: dict[str, str],
) -> tuple[Path, Path]:
    cobc = shutil.which("cobc")
    javac = shutil.which("javac")
    java = shutil.which("java")
    missing = [name for name, path in (("cobc", cobc), ("javac", javac), ("java", java)) if not path]
    if missing:
        raise VerificationError(f"Required compiler/runtime not found on PATH: {', '.join(missing)}")

    cobol_dir = root / "cobol"
    java_dir = root / "java"
    cobol_dir.mkdir()
    java_dir.mkdir()
    cobol_file = cobol_dir / "program.cob"
    cobol_file.write_text(cobol_src, encoding="utf-8")
    java_file = java_dir / "Main.java"
    java_file.write_text(java_src, encoding="utf-8")
    cobol_exe = cobol_dir / ("program.exe" if os.name == "nt" else "program")

    _require_success("COBOL compilation", _run([cobc, "-x", "-o", str(cobol_exe), str(cobol_file)], env=env))
    _require_success("Java compilation", _run([javac, "-d", str(java_dir), str(java_file)], env=env))
    return cobol_exe, java_dir


def verify(cobol_src: str, java_src: str, test_cases: list[TestCase]) -> VerificationReport:
    """Compile both programs once, then compare their output for each input case."""
    java = shutil.which("java")
    if not java:
        raise VerificationError("Required compiler/runtime not found on PATH: java")

    env = _compiler_environment()
    with tempfile.TemporaryDirectory(prefix="idem-verify-") as temporary_directory:
        cobol_exe, java_dir = _compile(cobol_src, java_src, Path(temporary_directory), env)
        results = []
        for test_case in test_cases:
            cobol_run = _run([str(cobol_exe)], input_text=test_case.stdin, env=env)
            _require_success(f"COBOL execution for {test_case.name}", cobol_run)
            java_run = _run([java, "-cp", str(java_dir), "Main"], input_text=test_case.stdin, env=env)
            _require_success(f"Java execution for {test_case.name}", java_run)
            cobol_output = _normalize(cobol_run.stdout)
            java_output = _normalize(java_run.stdout)
            results.append(
                CaseResult(
                    name=test_case.name,
                    cobol_output=cobol_output,
                    java_output=java_output,
                    match=cobol_output == java_output,
                )
            )

    passed = sum(result.match for result in results)
    return VerificationReport(results=results, passed=passed, failed=len(results) - passed)


def _sample_sources(sample_path: Path) -> tuple[str, str]:
    if sample_path.is_file():
        cobol_file = sample_path
        java_candidates = list(sample_path.parent.glob("*.java"))
    else:
        cobol_candidates = list(sample_path.glob("*.cob"))
        if len(cobol_candidates) != 1:
            raise VerificationError(f"Expected one .cob file in {sample_path}, found {len(cobol_candidates)}")
        cobol_file = cobol_candidates[0]
        java_candidates = list(sample_path.glob("*.java"))
    if len(java_candidates) != 1:
        raise VerificationError(f"Expected one .java file beside {cobol_file}, found {len(java_candidates)}")
    return cobol_file.read_text(encoding="utf-8"), java_candidates[0].read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile and compare a COBOL/Java sample.")
    parser.add_argument("sample", type=Path, help="sample directory or COBOL source file")
    args = parser.parse_args()

    try:
        cobol_src, java_src = _sample_sources(args.sample)
        report = verify(cobol_src, java_src, [TestCase(name="typical", stdin="10000\n5\n36\n")])
    except (OSError, VerificationError) as exc:
        print(f"Verification error:\n{exc}", file=sys.stderr)
        return 1

    for result in report.results:
        status = "PASS" if result.match else "FAIL"
        print(f"[{status}] {result.name}")
        print("COBOL stdout:")
        print(result.cobol_output)
        print("Java stdout:")
        print(result.java_output)
    print(f"Verification: {report.passed}/{len(report.results)} passed")
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())