"""Test proposal generation and file-writing adapters (CG-07, CG-08)."""

from .defective_seeds import CompositeProposalSource, DefectiveSeedProposalSource
from .file_reader import FileProposalReader
from .file_writer import MANIFEST_FILE_NAME, FileProposalWriter
from .template_source import DEFAULT_REL_TOL, TemplateProposalSource

__all__ = [
    "DEFAULT_REL_TOL",
    "MANIFEST_FILE_NAME",
    "CompositeProposalSource",
    "DefectiveSeedProposalSource",
    "FileProposalReader",
    "FileProposalWriter",
    "TemplateProposalSource",
]
