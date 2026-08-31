from tools.mac_pyinstaller_filters import (
    collect_pkg_without_metadata,
    filter_toc,
    is_codesign_poison,
)


def test_is_codesign_poison():
    assert is_codesign_poison("/app/Contents/Frameworks/fastapi-0.110.0.dist-info")
    assert is_codesign_poison("/app/Contents/Resources/uvicorn-0.29.0.dist-info")
    assert is_codesign_poison("/app/Contents/Frameworks/._fastapi-0.110.0.dist-info")
    assert not is_codesign_poison("/app/Contents/Resources/fastapi/routing.py")
    assert not is_codesign_poison("/app/Contents/Frameworks/libpython3.9.dylib")


def test_filter_toc_drops_metadata():
    toc = [
        ("/venv/fastapi-0.110.0.dist-info", "fastapi-0.110.0.dist-info", "DATA"),
        ("/venv/fastapi/__init__.py", "fastapi", "DATA"),
    ]
    out = filter_toc(toc)
    assert len(out) == 1
    assert out[0][0].endswith("__init__.py")


def test_collect_pkg_without_metadata():
    def fake_collect(_pkg):
        return (
            [("pkg-1.0.dist-info", ".", "DATA"), ("pkg/mod.py", "pkg", "DATA")],
            [],
            ["pkg.mod"],
        )

    datas, binaries, hidden = collect_pkg_without_metadata(fake_collect, "pkg")
    assert len(datas) == 1
    assert datas[0][0].endswith("mod.py")
    assert binaries == []
    assert hidden == ["pkg.mod"]
