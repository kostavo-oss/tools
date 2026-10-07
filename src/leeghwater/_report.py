"""What dlt reports about a load, as one block. `spec/001`, R7."""

import re
from typing import Any


def _size(size: int | None) -> str:
    if size is None:
        return "?"
    amount = float(size)
    for unit in ("B", "kB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{size} B"


def _reason(message: str | None) -> str:
    """One line of why a job failed. dlt gives the whole traceback as the message."""
    lines = [line.strip() for line in (message or "").splitlines() if line.strip()]
    if not lines:
        return "dlt gave no reason"
    if not lines[0].startswith("Traceback"):
        return lines[0]
    errors = [line for line in lines if re.match(r"[\w.]+(Error|Exception)\w*: ", line)]
    return errors[-1] if errors else lines[-1]


def is_load_info(result: Any) -> bool:
    return hasattr(result, "load_packages") and hasattr(result, "has_failed_jobs")


def failed_jobs(load_info: Any) -> list[Any]:
    return [
        job for package in load_info.load_packages for job in package.jobs["failed_jobs"]
    ]


def load_report(load_info: Any) -> str:
    """dlt's `LoadInfo` as lines: packages, their jobs, and where it all went.

    https://dlthub.com/docs/running-in-production/running#inspect-and-save-the-load-info-and-trace
    """
    lines = ["load report"]
    if not load_info.load_packages:
        lines.append("  nothing to load: the source gave no rows")
    for package in load_info.load_packages:
        lines.append(f"  package {package.load_id}: {package.state}")
        done = package.jobs["completed_jobs"]
        infos = [job.job_file_info for job in done]
        table = max((len(info.table_name) for info in infos), default=0)
        kind = max((len(info.file_format) for info in infos), default=0)
        for job, info in zip(done, infos, strict=True):
            lines.append(
                f"    done    {info.table_name:<{table}}  {info.file_format:<{kind}}"
                f"  {_size(job.file_size):>9}  {job.elapsed:.1f}s"
            )
        for job in package.jobs["failed_jobs"]:
            reason = _reason(job.failed_message)
            lines.append(f"    FAILED  {job.job_file_info.table_name}: {reason}")
    lines.append(f"  destination  {load_info.destination_type}")
    lines.append(f"  schema       {load_info.dataset_name}")
    if load_info.started_at and load_info.finished_at:
        lines.append(f"  started      {load_info.started_at:%Y-%m-%d %H:%M:%S %Z}")
        lines.append(f"  finished     {load_info.finished_at:%Y-%m-%d %H:%M:%S %Z}")
    if load_info.first_run:
        lines.append("  first run    yes: this pipeline had no state before")
    return "\n".join(lines)
