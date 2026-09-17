from __future__ import annotations

import unittest
from pathlib import Path

from ag2_system.core import ExperimentConfig, MedCase, load_cases, load_experiment_config
from ag2_system.orchestration.run_many_agent import run_many_agent_case


ROOT = Path(__file__).resolve().parents[1]


class StandaloneSmokeTests(unittest.TestCase):
    def test_default_config_and_dataset_load(self) -> None:
        config = load_experiment_config(ROOT / "configs" / "experiment.json")
        cases = load_cases(config.dataset_path)
        self.assertEqual(config.stage, "initial")
        self.assertTrue(cases)

    def test_mock_many_agent_flow(self) -> None:
        config = load_experiment_config(ROOT / "configs" / "experiment.json")
        config.mock = True
        config.many_agent["top_k_committees"] = 2
        config.many_agent["min_k_committees"] = 2
        config.many_agent["max_k_committees"] = 2
        case = MedCase(
            case_type="rare_disease",
            case_name="mock",
            case_url="mock-1",
            initial_presentation="Newborn with seizures, hypotonia, congenital anomalies and a suspected gene variant.",
            follow_up_presentation="Follow-up genetic testing remains inconclusive.",
        )
        result = run_many_agent_case(case, config)
        canonical = result.metadata["canonical_result"]
        activated = canonical["metadata"]["activated_committees"]
        summaries = canonical["committee_summaries"]
        self.assertEqual(len(activated), 2)
        self.assertEqual({item["committee_name"] for item in summaries}, set(activated))
        self.assertFalse(canonical["metadata"]["node_pollution_enabled"])
        self.assertEqual(canonical["metadata"]["baseline_source_commit"], "01826c0")


if __name__ == "__main__":
    unittest.main()
