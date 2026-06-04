from app.schemas import build_thread_id


def test_different_user_or_conversation_generates_different_thread_id() -> None:
    assert build_thread_id("u1", "c1") != build_thread_id("u1", "c2")
    assert build_thread_id("u1", "c1") != build_thread_id("u2", "c1")
    assert build_thread_id("u1", "") == "u1:default"
