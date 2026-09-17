from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


STAGE_ALIASES = {
    "initial": "initial",
    "follow_up": "follow_up",
    "follow-up": "follow_up",
    "followup": "follow_up",
}


def normalize_stage(stage: str) -> str:
    value = str(stage or "").strip().lower()
    try:
        return STAGE_ALIASES[value]
    except KeyError as exc:
        raise ValueError("stage must be 'initial' or 'follow_up'") from exc


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


@dataclass
class ExperimentConfig:
    model_provider: str = "openai"
    model_name: str = "gpt-4o-mini"
    stage: str = "initial"
    dataset_path: str = "data/sample_cases.json"
    output_dir: str = "output"
    mock: bool = False
    limit: int = 0
    many_agent: Dict[str, Any] = field(default_factory=dict)
    heterogeneous_models: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.stage = normalize_stage(self.stage)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentConfig":
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})

    def resolve_paths(self, project_root: Path) -> None:
        dataset = Path(self.dataset_path)
        output = Path(self.output_dir)
        if not dataset.is_absolute():
            self.dataset_path = str((project_root / dataset).resolve())
        if not output.is_absolute():
            self.output_dir = str((project_root / output).resolve())
        department_path = Path(
            self.many_agent.get("departments_config", "ag2_system/configs/departments.yaml")
        )
        if not department_path.is_absolute():
            self.many_agent["departments_config"] = str((project_root / department_path).resolve())


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {config_path}")
    config = ExperimentConfig.from_dict(data)
    project_root = config_path.parent.parent if config_path.parent.name == "configs" else config_path.parent
    config.resolve_paths(project_root)
    return config


@dataclass
class MedCase:
    case_type: str
    case_name: str
    case_url: str
    initial_presentation: str
    follow_up_presentation: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MedCase":
        def pick(*keys: str, default: str = "") -> str:
            for key in keys:
                if key in data and data[key] is not None:
                    return str(data[key])
            return default

        return cls(
            case_type=pick("case_type", "Type"),
            case_name=pick("case_name", "Final Name", "Name"),
            case_url=pick("case_id", "case_url", "Case URL", "Crl"),
            initial_presentation=pick("initial_presentation", "Initial Presentation"),
            follow_up_presentation=pick(
                "follow_up_presentation", "Follow-up Presentation", "Follow Up Presentation"
            ),
        )


def load_cases(path: str | Path) -> List[MedCase]:
    dataset_path = Path(path)
    with dataset_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    records = payload.get("Cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"Dataset must be a JSON list or an object with a Cases list: {dataset_path}")
    return [MedCase.from_dict(item) for item in records]


@dataclass
class CaseResult:
    case_type: str = ""
    case_url: str = ""
    case_name: str = ""
    stage: str = "initial"
    presentation: str = ""
    most_likely_diagnosis: str = ""
    differential_diagnoses: List[str] = field(default_factory=list)
    recommended_tests: List[str] = field(default_factory=list)
    areas_of_disagreement: List[str] = field(default_factory=list)
    total_cost: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.stage = normalize_stage(self.stage)
        self.case_url = str(self.case_url)
        self.differential_diagnoses = _as_list(self.differential_diagnoses)
        self.recommended_tests = _as_list(self.recommended_tests)
        self.areas_of_disagreement = _as_list(self.areas_of_disagreement)
        self.total_cost = float(self.total_cost or 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
