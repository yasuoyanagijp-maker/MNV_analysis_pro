# Pytest configuration for retinal-analysis-pro tests.
# Suppress PyparsingDeprecationWarning from matplotlib (dependency chain).


def pytest_configure(config):
    """matplotlib 経由の PyparsingDeprecationWarning を非表示にする。"""
    for msg in ("oneOf", "parseString", "resetCache"):
        config.addinivalue_line(
            "filterwarnings",
            f"ignore:{msg} deprecated:DeprecationWarning",
        )
