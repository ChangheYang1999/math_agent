"""Literature formalization and safe, application-controlled paper acquisition."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from .context_builder import prose
from .literature import PDFDownloader
from .schemas import BackgroundOutput

DESTINATIONS = {
    "problem_spec": "problem/specification.md",
    "literature_index": "literature/literature_index.md",
    "background_report": "reports/background_report.md",
    "agent_context": "literature/AGENT_CONTEXT.md",
}


class BackgroundRunner:
    def __init__(self, services: Any):
        self.s = services

    async def run(self, job_id: int, guard: Callable[[], None]) -> int:
        s = self.s
        metadata = {"project": s.db.project["slug"], "job": str(job_id), "role": "background"}
        result = await s.gateway.run_structured(
            role="background",
            action_key=f"background:{job_id}",
            input_text=s.paths.read("problem/original.md"),
            output_type=BackgroundOutput,
            metadata=metadata,
        )
        output = result.output
        staged = []
        for field, destination in DESTINATIONS.items():
            raw = getattr(output, field).content
            if field == "problem_spec":
                raw = f"# {output.normalized_problem_title}\n\n{raw}"
            artifact = await s.artifacts.persist(
                key=f"background:{job_id}:{field}",
                kind=field,
                scope=str(job_id),
                raw_content=raw,
                mode="aggressive",
                destination=destination,
                metadata=metadata,
                model_run_id=result.run_id,
                publish=False,
            )
            staged.append(artifact)
        references = []
        downloader = PDFDownloader(s.paths, s.config)
        for index, reference in enumerate(output.literature):
            identity = reference.model_dump(
                exclude={"relevance", "key_results", "theorem_locations", "limitations"}
            )
            stable = (
                reference.doi
                or reference.arxiv_id
                or reference.url
                or (reference.title + str(reference.year))
            )
            reference_key = hashlib.sha256(stable.encode()).hexdigest()
            notes = await s.artifacts.persist(
                key=f"background:{job_id}:paper:{index}",
                kind="literature_notes",
                scope=reference_key,
                raw_content=prose(
                    reference.model_dump(
                        include={"relevance", "key_results", "theorem_locations", "limitations"}
                    )
                ),
                mode="proof_safe",
                destination=f"literature/notes/{reference_key}.md",
                metadata=metadata,
                model_run_id=result.run_id,
                publish=False,
            )
            staged.append(notes)
            pdf_path = pdf_hash = error = None
            existing = s.db.one("SELECT * FROM literature WHERE reference_key=?", (reference_key,))
            if existing and existing["pdf_path"]:
                pdf_path, pdf_hash = existing["pdf_path"], existing["pdf_sha256"]
            elif reference.pdf_url and s.config.literature.download_open_access_pdfs:
                try:
                    downloaded = await downloader.download(reference.pdf_url, reference.title)
                    pdf_path, pdf_hash = downloaded.relative_path, downloaded.sha256
                except (ValueError, OSError, TimeoutError) as exc:
                    error = type(exc).__name__
            references.append((reference_key, identity, notes, pdf_path, pdf_hash, error))
        bibliography = output.references_bib
        if bibliography is None and output.literature:
            bibliography = "\n\n".join(bibtex(i, ref) for i, ref in enumerate(output.literature, 1))
        if bibliography:
            staged.append(
                await s.artifacts.persist(
                    key=f"background:{job_id}:bib",
                    kind="bibliography",
                    scope=str(job_id),
                    raw_content=bibliography,
                    mode="proof_safe",
                    destination="literature/references.bib",
                    metadata=metadata,
                    model_run_id=result.run_id,
                    publish=False,
                )
            )
        guard()
        with s.db.transaction() as c:
            guard(c)
            for reference_key, identity, notes, pdf_path, pdf_hash, error in references:
                c.execute(
                    "INSERT INTO literature(reference_key,metadata_json,notes_artifact_id,pdf_path,pdf_sha256,download_error) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(reference_key) DO UPDATE SET metadata_json=excluded.metadata_json,notes_artifact_id=excluded.notes_artifact_id,"
                    "pdf_path=excluded.pdf_path,pdf_sha256=excluded.pdf_sha256,download_error=excluded.download_error",
                    (
                        reference_key,
                        json.dumps(identity, ensure_ascii=False),
                        notes["id"],
                        pdf_path,
                        pdf_hash,
                        error,
                    ),
                )
        # All editing finished before any downstream background view is replaced.
        # A failed publication is recoverable by replaying these cached artifacts.
        for artifact in staged:
            s.artifacts.publish(artifact)
        return job_id


def bibtex(index: int, reference: Any) -> str:
    """Only known identity fields; generated descriptions never enter bibliography metadata."""

    def escape(value: Any) -> str:
        return str(value).replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}")

    fields = {"title": reference.title}
    if reference.authors:
        fields["author"] = " and ".join(reference.authors)
    for name in ("year", "doi", "url"):
        if getattr(reference, name) is not None:
            fields[name] = getattr(reference, name)
    return (
        "@misc{paper"
        + str(index)
        + ",\n"
        + ",\n".join(f"  {k} = {{{escape(v)}}}" for k, v in fields.items())
        + "\n}"
    )
