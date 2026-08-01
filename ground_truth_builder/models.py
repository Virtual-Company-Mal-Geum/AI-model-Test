from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedDocument:
    document_type: str
    title: str = ""
    author: str = ""
    published: str = ""
    publisher: str = ""
    main_content: str = ""
    sections: dict[str, str] = field(default_factory=dict)


@dataclass
class ProcessResult:
    record: dict[str, Any]
    report: dict[str, Any]

