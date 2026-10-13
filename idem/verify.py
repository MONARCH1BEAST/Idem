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


class VerificationTimeout(VerificationError):
    def __init__(self, message: str, stdout: bytes, stderr: bytes):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            input=input_text.encode("utf-8") if input_text is not None else None,
            capture_output=True,
            text=False,
            check=False,
            timeout=30,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8")
        raise VerificationTimeout(
            f"TIMEOUT after {exc.timeout} seconds: {' '.join(command)}",
            stdout,
            stderr,
        ) from exc
    except OSError as exc:
        raise VerificationError(f"Command failed: {' '.join(command)}\n{exc}") from exc


def _decode(output: bytes) -> str:
    return output.decode("utf-8", errors="replace")


def _require_success(stage: str, result: subprocess.CompletedProcess[bytes]) -> None:
    if result.returncode != 0:
        raise VerificationError(
            f"{stage} failed (exit {result.returncode})\n"
            f"stdout:\n{_decode(result.stdout)}\nstderr:\n{_decode(result.stderr)}"
        )


def _normalize(output: bytes) -> bytes:
    output = output.replace(b"\r\n", b"\n")
    return b"\n".join(line.rstrip() for line in output.split(b"\n")).rstrip(b"\n")


def _failure_results(test_cases: list[TestCase], reason: str, stderr: str) -> list[CaseResult]:
    return [
        CaseResult(
            name=test_case.name,
            cobol_output="",
            java_output="",
            match=False,
            stderr=stderr,
            reason=reason,
        )
        for test_case in test_cases
    ]


def _execute_case(
    command: list[str],
    stdin: str,
    label: str,
    env: dict[str, str],
) -> tuple[bytes, str, str]:
    try:
        result = _run(command, input_text=stdin, env=env)
    except VerificationTimeout as exc:
        return _normalize(exc.stdout), _decode(exc.stderr), f"TIMEOUT: {label} exceeded 30 seconds"
    except VerificationError as exc:
        return b"", str(exc), f"{label} execution error"

    reason = "" if result.returncode == 0 else f"{label} exited with code {result.returncode}"
    return _normalize(result.stdout), _decode(result.stderr), reason


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
    normalized_cobol = cobol_src.replace("\r\n", "\n").replace("\r", "\n")
    cobol_file.write_bytes(normalized_cobol.encode("utf-8"))
    java_file = java_dir / "Main.java"
    normalized_java = java_src.replace("\r\n", "\n").replace("\r", "\n")
    java_file.write_bytes(normalized_java.encode("utf-8"))
    cobol_exe = cobol_dir / ("program.exe" if os.name == "nt" else "program")

    _require_success("COBOL compilation", _run([cobc, "-x", "-o", str(cobol_exe), str(cobol_file)], env=env))
    _require_success("Java compilation", _run([javac, "-d", str(java_dir), str(java_file)], env=env))
    return cobol_exe, java_dir


def verify(cobol_src: str, java_src: str, test_cases: list[TestCase]) -> VerificationReport:
    """Compile both programs once, then compare their output for each input case."""
    java = shutil.which("java")
    if not java:
        results = _failure_results(
            test_cases,
            "COMPILATION ERROR",
            "Required compiler/runtime not found on PATH: java",
        )
        return _verification_report(results)

    env = _compiler_environment()
    with tempfile.TemporaryDirectory(prefix="idem-verify-") as temporary_directory:
        try:
            cobol_exe, java_dir = _compile(cobol_src, java_src, Path(temporary_directory), env)
        except VerificationTimeout as exc:
            diagnostic = _decode(exc.stderr) or str(exc)
            results = _failure_results(
                test_cases,
                "TIMEOUT: compilation exceeded 30 seconds",
                diagnostic.replace(temporary_directory, "<verification-temp>"),
            )
            return _verification_report(results)
        except VerificationError as exc:
            diagnostic = str(exc).replace(temporary_directory, "<verification-temp>")
            results = _failure_results(test_cases, "COMPILATION ERROR", diagnostic)
            return _verification_report(results)

        results = []
        for test_case in test_cases:
            cobol_bytes, cobol_stderr, cobol_reason = _execute_case(
                [str(cobol_exe)],
                test_case.stdin,
                "COBOL",
                env,
            )
            java_bytes, java_stderr, java_reason = _execute_case(
                [java, "-cp", str(java_dir), "Main"],
                test_case.stdin,
                "Java",
                env,
            )
            stderr = "\n".join(
                f"{label} stderr:\n{output}"
                for label, output in (("COBOL", cobol_stderr), ("Java", java_stderr))
                if output
            )
            reasons = [reason for reason in (cobol_reason, java_reason) if reason]
            match = not reasons and cobol_bytes == java_bytes
            reason = "; ".join(reasons)
            if not match and not reason:
                reason = (
                    f"stdout mismatch: cobol={len(cobol_bytes)}B "
                    f"java={len(java_bytes)}B"
                )
            results.append(
                CaseResult(
                    name=test_case.name,
                    cobol_output=_decode(cobol_bytes),
                    java_output=_decode(java_bytes),
                    match=match,
                    stderr=stderr,
                    reason=reason,
                )
            )

    return _verification_report(results)


def _verification_report(results: list[CaseResult]) -> VerificationReport:
    passed = sum(result.match for result in results)
    failed = len(results) - passed
    assert passed + failed == len(results)
    return VerificationReport(results=results, passed=passed, failed=failed)


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