from localflow.main import _error_code


def test_error_code_mapping_for_common_statuses():
    assert _error_code(400) == "INVALID_REQUEST"
    assert _error_code(404) == "NOT_FOUND"
    assert _error_code(409) == "CONFLICT"
    assert _error_code(422) == "VALIDATION_ERROR"
    assert _error_code(500) == "INTERNAL_ERROR"
