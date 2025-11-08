from main import add
import pytest


def test_add():
    assert add(2, 3) == 5, "2+3 should be 5"
    with pytest.raises(ValueError, match="a should not be 1"):
        add(1, 3)
