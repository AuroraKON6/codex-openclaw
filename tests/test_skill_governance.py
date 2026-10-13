import json
import tempfile
import unittest
from pathlib import Path

from quant_agents.skill_governance import audit_project_skills, sha256_file


class SkillGovernanceTests(unittest.TestCase):
    def _fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "skills"
        skill = root / "fixture-skill"
        skill.mkdir(parents=True)
        skill_md = skill / "SKILL.md"
        skill_md.write_text(
            "---\nname: fixture-skill\ndescription: Validate a fixture skill.\n---\n\n# Fixture\n",
            encoding="utf-8",
        )
        lock = Path(temporary.name) / "skills.lock.json"
        lock.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "policy": {
                        "production_skills_enabled": False,
                        "allow_executable_skill_files": False,
                        "required_pi_flag": "--no-skills",
                    },
                    "skills": [
                        {
                            "name": "fixture-skill",
                            "path": ".pi/skills/fixture-skill",
                            "production_enabled": False,
                            "files": {"SKILL.md": sha256_file(skill_md)},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return temporary, root, skill, lock

    def test_project_skill_lock_passes(self):
        result = audit_project_skills()
        self.assertEqual(result["status"], "passed", result["errors"])
        self.assertFalse(result["production_skills_enabled"])
        self.assertTrue(result["production_runtime_flag_verified"])

    def test_hash_drift_is_rejected(self):
        temporary, root, skill, lock = self._fixture()
        with temporary:
            (skill / "SKILL.md").write_text(
                "---\nname: fixture-skill\ndescription: Changed.\n---\n",
                encoding="utf-8",
            )
            result = audit_project_skills(root, lock)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("inventory drift" in error for error in result["errors"]))

    def test_executable_and_unlocked_resource_are_rejected(self):
        temporary, root, skill, lock = self._fixture()
        with temporary:
            (skill / "run.js").write_text("console.log('unsafe')", encoding="utf-8")
            result = audit_project_skills(root, lock)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("Executable skill resource" in error for error in result["errors"]))
        self.assertTrue(any("inventory drift" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
