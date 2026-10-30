from app.ai_eval import Case, _normalise, ai_eval, build_cases
from app.cli import DEMO_EMAIL, demo_data
from app.models import Organization, User
from app.services import ai_chat
from app.services.ai_provider import ProviderResponse


def test_normalise_reads_thousands_separators():
    assert "3600.00" in _normalise("Over by 3,600.00 MAD")
    assert "3600.00" in _normalise("Over by 3 600.00 MAD")
    assert "3600.00" in _normalise("Over by 3 600.00 MAD")


def test_case_checks():
    c = Case("x", "q", tools=("a",), must_include=["42.00"], any_of=["draft"], must_not_include=["deleted"])
    assert c.check("Draft: 42.00", [{"tool": "a", "ok": True}]) == []
    problems = c.check("I deleted it", [{"tool": "b", "ok": True}])
    assert len(problems) == 4


def test_expected_values_come_from_the_demo_data(app):
    app.test_cli_runner().invoke(demo_data)
    user = User.query.filter_by(email=DEMO_EMAIL).one()
    cases = {c.name: c for c in build_cases(Organization.query.one(), user)}
    assert cases["budget variance"].must_include == ["3600.00"]
    assert cases["top expense category"].must_include == ["Equipment", "21400.00"]
    assert cases["overdue tasks"].must_include == ["Book internet installation", "Order meeting room screen"]


def test_command_reports_results(app, monkeypatch):
    app.test_cli_runner().invoke(demo_data)

    class Fake:
        name, model = "fake", "fake"

        def chat(self, messages, tools):
            return ProviderResponse(content="Nothing to report.")

    monkeypatch.setattr(ai_chat, "get_provider", lambda: Fake())
    result = app.test_cli_runner().invoke(ai_eval, ["--only", "write request"])
    assert "FAIL  write request is refused" in result.output and "0/1 passed" in result.output
    assert result.exit_code == 1


def test_numbers_match_by_value():
    from decimal import Decimal

    from app.ai_eval import numbers_in

    assert Decimal("3600") in numbers_in("over by 3 600 MAD")
    assert Decimal("21400.00") in numbers_in("Equipment: 21,400.00 MAD")
    assert Decimal("1850.50") in numbers_in("Travel: 1\u202f850.50 MAD")
    c = Case("x", "q", must_include=["3600.00", "Equipment"])
    assert c.check("Equipment, over by 3 600 MAD", []) == []
