import json
from pathlib import Path
from code_form.analyzer import analyze_repository, write_bundle

def test_analyzer_extracts_symbols_imports_and_evidence(tmp_path: Path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "service.py").write_text("from pkg import helper\n\nclass Service:\n    def run(self):\n        return helper()\n", encoding="utf-8")
    (pkg / "helper.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    (tmp_path / "main.py").write_text('if __name__ == "__main__":\n    print("hello")\n', encoding="utf-8")
    bundle = analyze_repository(tmp_path)
    assert bundle["scope"]["read_only"] is True
    assert bundle["scope"]["executed_project_code"] is False
    assert bundle["summary"]["file_count"] == 4
    assert bundle["summary"]["python_file_count"] == 4
    symbol = next(s for f in bundle["files"] if f["path"] == "pkg/service.py" for s in f["python"]["symbols"] if s["name"] == "Service")
    assert symbol["evidence"]["line_start"] == 3
    assert any("main.py contains" in claim["statement"] for claim in bundle["claims"])
    assert "flowchart LR" in bundle["diagrams"]["dependency_graph_mermaid"]

def test_parse_errors_are_observations(tmp_path: Path):
    (tmp_path / "broken.py").write_text("def nope(:\n", encoding="utf-8")
    bundle = analyze_repository(tmp_path)
    assert bundle["summary"]["python_parse_error_count"] == 1
    assert bundle["claims"][0]["status"] == "observed"
    assert bundle["claims"][0]["evidence"][0]["line_start"] == 1

def test_json_bundle_is_deterministic(tmp_path: Path):
    (tmp_path / "hello.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
    first, second = analyze_repository(tmp_path), analyze_repository(tmp_path)
    assert first == second
    output = tmp_path / "out" / "analysis.json"
    write_bundle(first, output)
    assert json.loads(output.read_text(encoding="utf-8")) == first
