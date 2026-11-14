from agent import verify_output


def test_verification_bug_is_visible_to_the_demo():
    assert verify_output({"ok": False}) is True
