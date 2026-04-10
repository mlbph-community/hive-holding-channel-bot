from app.utils import extract_message_id_from_link

def test_extract_message_id_from_t_me_c_link():
    assert extract_message_id_from_link("https://t.me/c/123456789/456") == 456

def test_extract_message_id_from_public_link():
    assert extract_message_id_from_link("https://t.me/examplechannel/789") == 789
