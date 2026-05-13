from n8n_backup_restore.utils.files import sanitize_filename


def test_sanitize_filename_replaces_invalid_chars() -> None:
    assert sanitize_filename('ab:c/1*2?"3') == "ab_c_1_2__3"


def test_sanitize_filename_fallback() -> None:
    assert sanitize_filename("   ") == "sem_nome"
