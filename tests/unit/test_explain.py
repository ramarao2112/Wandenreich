"""Stage 3 unit tests — rule documentation and CLI explain command."""

from __future__ import annotations

import pytest

from trustc.cli import main
from trustc.rules_doc import RULES_INFO, get_rule_doc

pytestmark = pytest.mark.stage3


class TestRuleDocumentation:
    @pytest.mark.parametrize("rule_id", ["TC-001", "TC-002", "TC-003", "TC-004", "TC-005"])
    def test_all_five_rules_documented(self, rule_id: str):
        doc = get_rule_doc(rule_id)
        assert f"# {rule_id}:" in doc
        assert "## Overview" in doc
        assert "## Trigger" in doc
        assert "## Fix Options" in doc

    def test_case_insensitive_lookup(self):
        doc_upper = get_rule_doc("TC-001")
        doc_lower = get_rule_doc("tc-001")
        assert doc_upper == doc_lower

    def test_unknown_rule_raises_key_error(self):
        with pytest.raises(KeyError, match="Unknown rule ID 'TC-999'"):
            get_rule_doc("TC-999")

    def test_rules_info_completeness(self):
        assert len(RULES_INFO) == 5
        for r_id, info in RULES_INFO.items():
            assert info["id"] == r_id
            assert "name" in info
            assert "shortDescription" in info
            assert "fullDescription" in info
            assert "helpUri" in info


class TestExplainCLI:
    def test_cli_explain_success(self, capsys):
        rc = main(["explain", "TC-002"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "# TC-002: OWNERSHIP-CHECK" in captured.out

    def test_cli_explain_unknown_rule_exit_2(self, capsys):
        rc = main(["explain", "TC-999"])
        assert rc == 2
        captured = capsys.readouterr()
        assert "Unknown rule ID" in captured.err
