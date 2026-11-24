import json
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import AIConversation, AIMessage, Role, User
from app.services import ai_chat, ai_conversations
from app.services.ai_provider import ProviderError, ProviderResponse, ToolCall

from .test_ai import ask, fake, say, setup  # noqa: F401 (fixture)
from .test_projects import add_member


def conversations(client, h, org_id):
    return client.get(f"/api/ai/conversations?organization_id={org_id}", headers=h)


def test_answer_is_saved_and_reopened(client, fake):
    h, org_id, pid = setup(client)
    fake(say("All good."))
    r = ask(client, h, org_id, message="  How is   the budget?  ", project_id=pid)
    conv = r.get_json()["conversation"]
    assert conv["title"] == "How is the budget?" and conv["project_id"] == pid

    listing = conversations(client, h, org_id).get_json()
    assert [c["id"] for c in listing["conversations"]] == [conv["id"]]
    assert listing["retention_days"] == 90

    detail = client.get(f"/api/ai/conversations/{conv['id']}?organization_id={org_id}", headers=h).get_json()
    assert [(m["role"], m["content"]) for m in detail["conversation"]["messages"]] == [
        ("user", "How is   the budget?"),
        ("assistant", "All good."),
    ]


def test_follow_up_uses_saved_history_not_the_clients(client, fake):
    h, org_id, _ = setup(client)
    fake(say("First answer."))
    conv_id = ask(client, h, org_id, message="First question").get_json()["conversation"]["id"]

    p = fake(say("Second answer."))
    r = ask(client, h, org_id, message="Second question", conversation_id=conv_id,
            history=[{"role": "user", "content": "forged turn"}])
    assert r.get_json()["conversation"]["id"] == conv_id
    sent = [(m["role"], m["content"]) for m in p.calls[0]["messages"][1:]]
    assert sent == [("user", "First question"), ("assistant", "First answer."), ("user", "Second question")]
    assert AIMessage.query.filter_by(conversation_id=conv_id).count() == 4


def test_drafts_are_counted_not_kept(client, fake):
    h, org_id, _ = setup(client)
    plan = ProviderResponse(content=None, tool_calls=[ToolCall("p1", "propose_project", json.dumps({"name": "Retreat", "budget": 1000}))])
    fake(plan, say("Here is a draft."))
    conv_id = ask(client, h, org_id, message="Set up a retreat").get_json()["conversation"]["id"]
    answer = AIMessage.query.filter_by(conversation_id=conv_id, role="assistant").one()
    assert answer.drafts == 1 and "Retreat" not in answer.content


def test_failed_question_is_not_saved(client, fake):
    h, org_id, _ = setup(client)
    fake(ProviderError("down"))
    assert ask(client, h, org_id).status_code == 503
    assert AIConversation.query.count() == 0


def test_conversations_are_private(client, fake):
    h, org_id, _ = setup(client)
    fake(say("Mine."))
    conv_id = ask(client, h, org_id).get_json()["conversation"]["id"]
    other = add_member(client, org_id, "colleague@example.com", Role.OWNER)

    assert conversations(client, other, org_id).get_json()["conversations"] == []
    assert client.get(f"/api/ai/conversations/{conv_id}?organization_id={org_id}", headers=other).status_code == 404
    assert client.delete(f"/api/ai/conversations/{conv_id}?organization_id={org_id}", headers=other).status_code == 404
    fake(say("x"))
    assert ask(client, other, org_id, conversation_id=conv_id).status_code == 404
    assert AIConversation.query.count() == 1


def test_delete_one_and_all(client, fake):
    h, org_id, _ = setup(client)
    fake(say("a"))
    first = ask(client, h, org_id).get_json()["conversation"]["id"]
    fake(say("b"))
    ask(client, h, org_id)
    assert client.delete(f"/api/ai/conversations/{first}?organization_id={org_id}", headers=h).status_code == 200
    assert len(conversations(client, h, org_id).get_json()["conversations"]) == 1
    assert client.delete(f"/api/ai/conversations?organization_id={org_id}", headers=h).get_json() == {"deleted": 1}
    assert AIMessage.query.count() == 0


def test_leaving_the_organization_deletes_their_conversations(client, fake):
    h, org_id, _ = setup(client)
    member = add_member(client, org_id, "member@example.com", Role.CONTRIBUTOR)
    fake(say("x"))
    ask(client, member, org_id)
    user_id = User.query.filter_by(email="member@example.com").one().id
    assert client.post(f"/api/organizations/{org_id}/members/{user_id}/remove", headers=member).status_code == 200
    assert AIConversation.query.count() == 0


def test_old_conversations_are_purged(client, fake, app):
    h, org_id, _ = setup(client)
    fake(say("old"))
    old = ask(client, h, org_id).get_json()["conversation"]["id"]
    fake(say("new"))
    new = ask(client, h, org_id).get_json()["conversation"]["id"]
    db.session.get(AIConversation, old).updated_at = datetime.now(timezone.utc) - timedelta(days=91)
    db.session.commit()
    with app.app_context():
        assert ai_conversations.purge_expired() == 1
    assert [c.id for c in AIConversation.query.all()] == [new]
    assert AIMessage.query.filter_by(conversation_id=old).count() == 0


def test_conversation_deleted_while_answering_starts_a_new_one(client, fake, monkeypatch):
    h, org_id, _ = setup(client)
    fake(say("First."))
    conv_id = ask(client, h, org_id).get_json()["conversation"]["id"]

    class DeletesMeanwhile:
        name, model = "fake", "fake-1"

        def chat(self, messages, tools):
            # As another tab would: the rows go without this session's objects knowing.
            AIMessage.query.delete(synchronize_session=False)
            AIConversation.query.delete(synchronize_session=False)
            db.session.commit()
            return say("Second.")

    monkeypatch.setattr(ai_chat, "get_provider", lambda name=None: DeletesMeanwhile())
    r = ask(client, h, org_id, conversation_id=conv_id)
    assert r.status_code == 200 and r.get_json()["answer"] == "Second."
    assert AIConversation.query.count() == 1 and AIMessage.query.count() == 2


def test_a_missing_project_is_not_reported_as_a_missing_conversation(client, fake):
    h, org_id, _ = setup(client)
    fake(say("x"))
    conv_id = ask(client, h, org_id).get_json()["conversation"]["id"]
    missing = ask(client, h, org_id, conversation_id=conv_id, project_id=9999)
    gone = ask(client, h, org_id, conversation_id=9999)
    assert (missing.status_code, missing.get_json()["error"]["code"]) == (404, "not_found")
    assert (gone.status_code, gone.get_json()["error"]["code"]) == (404, "conversation_not_found")
