"""수동 공개 게시 준비 코드만 실행한다. 실제 키·DART·GH·회원 호출은 금지한다."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import socket
import subprocess
import urllib.parse
import urllib.request
import zipfile

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/member_map_judgments.yml"
SOURCE_ID = "source:dart:20260330000218"
KEY = "synthetic-key-must-not-be-logged"


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _code():
    steps = _workflow()["jobs"]["publish-reviewed"]["steps"]
    run = next(s["run"] for s in steps if s.get("name") == "공개 보고기간 원문 준비")
    assert run.startswith("python3 - <<'PY'\n") and run.endswith("\nPY\n")
    return run.split("\n", 1)[1].rsplit("\nPY\n", 1)[0]


@pytest.fixture(autouse=True)
def _isolate_data_dir(monkeypatch):
    # 기존 계좌·가격 fixture를 실행하지 않고 실제 네트워크 시도도 막는다.
    def denied(*args, **kwargs):
        raise AssertionError("실제 네트워크 금지")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)


class Environment(dict):
    def __init__(self, values):
        super().__init__(values)
        self.key_reads = 0

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key in {"PERIOD_DOCUMENTS", "PERIOD_REGISTRY", "GITHUB_EVENT_PATH"} and "GITHUB_EVENT_PATH" in self:
            # 합성 event 파일만 준비한다. 실제 GH 환경/입력은 읽지 않는다.
            event = {"inputs": {"period_documents": self["PERIOD_DOCUMENTS"],
                                "period_registry": self["PERIOD_REGISTRY"]}}
            Path(self["GITHUB_EVENT_PATH"]).write_text(json.dumps(event), encoding="utf-8")

    def get(self, key, default=None):
        if key == "DART_API_KEY":
            self.key_reads += 1
        return super().get(key, default)


class Response(BytesIO):
    def __init__(self, body, url, *, status=200, length=None):
        super().__init__(body)
        self.status = status
        self.url = url
        self.headers = {} if length is None else {"Content-Length": length}
        self.read_limits = []

    def geturl(self):
        return self.url

    def read(self, size=-1):
        self.read_limits.append(size)
        return super().read(size)


class Transport:
    def __init__(self, body, *, status=200, length=None, redirected=False, error=False):
        self.body, self.status, self.length = body, status, length
        self.redirected, self.error = redirected, error
        self.calls, self.responses = [], []

    def open(self, request, *, timeout):
        self.calls.append((request.full_url, timeout))
        if self.error:
            raise TimeoutError(KEY + " 원문 출력 금지")
        url = "https://invalid.example/" if self.redirected else request.full_url
        response = Response(self.body, url, status=self.status, length=self.length)
        self.responses.append(response)
        return response


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    runner = tmp_path / "runner"
    runner.mkdir()
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("20260330000218.xml", "<DOCUMENT>공개 합성 원문</DOCUMENT>".encode())
    archive = output.getvalue()
    document = {"source_id": SOURCE_ID, "issuer_id": "KR:111111", "issuer_name": "공개회사",
                "as_of": "2026-03-30", "url": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260330000218",
                "text": "당사의 주요 고객은 공개고객입니다.",
                "counterparties": [{"id": "KR:222222", "name": "공개고객"}]}
    version = sha256(json.dumps(document, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    context = {"schema": "reported-customer-period-v1", "source_id": SOURCE_ID,
               "company_id": "KR:111111", "counterparty_id": "KR:222222", "source_version": version,
               "corp_code": "01111111", "archive_sha256": sha256(archive).hexdigest()}
    row = {"source_id": SOURCE_ID, "company_id": "KR:111111", "counterparty_id": "KR:222222",
           "source_version": version, "source_url": document["url"], "published_on": document["as_of"],
           "period_context_v3": context}
    artifact = {"company_judgments": {"judgments": [row]}}
    env = Environment({"PERIOD_DOCUMENTS": json.dumps([document], ensure_ascii=False),
                       "PERIOD_REGISTRY": json.dumps({"KR:111111": {"name": "공개회사", "corp_code": "01111111"}}),
                       "DART_API_KEY": KEY, "REPLACE_SHA256": "a" * 64,
                       "RUNNER_TEMP": str(runner), "GITHUB_ENV": str(tmp_path / "github-env")})
    env["GITHUB_EVENT_PATH"] = str(tmp_path / "event.json")
    def save_artifact():
        body = json.dumps(artifact, ensure_ascii=False, allow_nan=False).encode()
        (tmp_path / "data/member_map_ai_candidates.json").write_bytes(body)
        env["ARTIFACT_SHA256"] = sha256(body).hexdigest()
    save_artifact()
    namespace = {"__name__": "period_workflow_test"}
    exec(compile(_code(), str(WORKFLOW), "exec"), namespace)
    return namespace, env, artifact, document, archive, save_artifact


def test_prepares_only_three_paths_and_preserves_original_bytes(prepared, capsys):
    namespace, env, _, document, archive, _ = prepared
    transport = Transport(archive, length=str(len(archive)))
    namespace["prepare"](env, opener=transport)
    assert env.key_reads == 1 and len(transport.calls) == 1
    url, timeout = transport.calls[0]
    parsed = urllib.parse.urlsplit(url)
    assert (parsed.scheme, parsed.netloc, parsed.path, timeout) == (
        "https", "opendart.fss.or.kr", "/api/document.xml", 25)
    assert urllib.parse.parse_qs(parsed.query) == {"crtfc_key": [KEY], "rcept_no": ["20260330000218"]}
    assert transport.responses[0].read_limits == [4 * 1024 * 1024 + 1]
    paths = dict(line.split("=", 1) for line in Path(env["GITHUB_ENV"]).read_text().splitlines())
    assert set(paths) == {"PERIOD_INPUT_PATH", "PERIOD_SOURCE_DIR", "PERIOD_REGISTRY_PATH"}
    directory = Path(paths["PERIOD_SOURCE_DIR"])
    assert directory.parent == Path(env["RUNNER_TEMP"]) and directory.stat().st_mode & 0o077 == 0
    assert {p.name for p in directory.iterdir()} == {
        "period-input.json", "issuer-registry.json", "dart-document-20260330000218.zip"}
    assert json.loads(Path(paths["PERIOD_INPUT_PATH"]).read_text()) == {"documents": [document]}
    assert set(json.loads(Path(paths["PERIOD_REGISTRY_PATH"]).read_text())["KR:111111"]) == {"name", "corp_code"}
    assert (directory / "dart-document-20260330000218.zip").read_bytes() == archive
    assert capsys.readouterr() == ("", "")


def test_eight_sources_and_repeated_same_source_fetch_once(prepared):
    namespace, env, artifact, document, archive, save = prepared
    original_row = deepcopy(artifact["company_judgments"]["judgments"][0])
    documents, rows = [], []
    for index in range(8):
        source = deepcopy(document)
        receipt = "20260330" + str(index).zfill(6)
        source["source_id"] = "source:dart:" + receipt
        source["url"] = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receipt
        version = sha256(json.dumps(source, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        row = deepcopy(original_row)
        row.update(source_id=source["source_id"], source_url=source["url"], source_version=version)
        row["period_context_v3"].update(source_id=source["source_id"], source_version=version)
        documents.append(source)
        rows.append(row)
    # 준비 단계의 호출 분모만 검사한다. 합성 ZIP의 원문 의미를 검수했다고 주장하지 않는다.
    artifact["company_judgments"]["judgments"] = rows + [deepcopy(rows[0])]
    env["PERIOD_DOCUMENTS"] = json.dumps(documents)
    save()
    transport = Transport(archive)
    namespace["prepare"](env, opener=transport)
    assert len(transport.calls) == 8 and env.key_reads == 1
    assert len({url for url, _ in transport.calls}) == 8


@pytest.mark.parametrize("legacy", [True, False])
def test_no_inputs_keep_legacy_or_missing_v3_for_existing_validator(prepared, legacy):
    namespace, env, artifact, _, archive, save = prepared
    env["PERIOD_DOCUMENTS"] = env["PERIOD_REGISTRY"] = ""
    if legacy:
        artifact["company_judgments"]["judgments"][0].pop("period_context_v3")
        save()
    transport = Transport(archive)
    namespace["prepare"](env, opener=transport)
    assert env.key_reads == 0 and transport.calls == []
    assert not Path(env["GITHUB_ENV"]).exists() and not list(Path(env["RUNNER_TEMP"]).iterdir())


@pytest.mark.parametrize("case", ["documents-only", "registry-only", "duplicate-doc", "duplicate-registry",
    "nan", "infinity", "overflow", "docs-size", "padded-docs-size", "registry-size", "answer-field", "too-many", "duplicate-id",
    "receipt-nonascii", "source-url", "issuer", "registry-name", "registry-corp", "unused-registry",
    "source-version", "compact-version", "context-source", "context-company", "context-counterparty",
    "context-corp", "row-url", "row-date", "archive-hash", "conflicting-archive", "unused-source",
    "artifact-hash", "prior-hash", "legacy-with-inputs"])
def test_rejects_bad_inputs_before_key_or_transport(prepared, case):
    namespace, env, artifact, document, archive, save = prepared
    row = artifact["company_judgments"]["judgments"][0]
    docs, registry = json.loads(env["PERIOD_DOCUMENTS"]), json.loads(env["PERIOD_REGISTRY"])
    if case == "too-many":
        docs *= 9
    elif case == "duplicate-id":
        docs *= 2
    elif case == "answer-field":
        docs[0]["answer"] = "비공개 입력 금지"
    elif case == "receipt-nonascii":
        docs[0]["source_id"] = "source:dart:２０２６０３３００００２１８"
    elif case == "source-url":
        docs[0]["url"] = "https://invalid.example/"
    elif case == "issuer":
        row["company_id"] = "KR:333333"
    elif case == "registry-name":
        registry["KR:111111"]["name"] = "다른 회사"
    elif case == "registry-corp":
        registry["KR:111111"]["corp_code"] = "１２３４５６７８"
    elif case == "unused-registry":
        registry["KR:333333"] = deepcopy(registry["KR:111111"])
    elif case == "source-version":
        row["source_version"] = "b" * 64
    elif case == "compact-version":
        version = sha256(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        row["source_version"] = row["period_context_v3"]["source_version"] = version
    elif case.startswith("context-"):
        field = {"source": "source_id", "company": "company_id", "counterparty": "counterparty_id", "corp": "corp_code"}[case[8:]]
        row["period_context_v3"][field] = "다른 값"
    elif case == "row-url":
        row["source_url"] = "https://invalid.example/"
    elif case == "row-date":
        row["published_on"] = "2026-03-29"
    elif case == "archive-hash":
        row["period_context_v3"]["archive_sha256"] = "not-a-hash"
    elif case == "conflicting-archive":
        second = deepcopy(row)
        second["period_context_v3"]["archive_sha256"] = "b" * 64
        artifact["company_judgments"]["judgments"].append(second)
    elif case == "unused-source":
        row["source_id"] = "source:dart:20260330000219"
    elif case == "legacy-with-inputs":
        row.pop("period_context_v3")
    env["PERIOD_DOCUMENTS"], env["PERIOD_REGISTRY"] = json.dumps(docs), json.dumps(registry)
    if case == "documents-only":
        env["PERIOD_REGISTRY"] = ""
    elif case == "registry-only":
        env["PERIOD_DOCUMENTS"] = ""
    elif case == "duplicate-doc":
        env["PERIOD_DOCUMENTS"] = '[{"source_id":"first","source_id":"second"}]'
    elif case == "duplicate-registry":
        env["PERIOD_REGISTRY"] = '{"KR:111111":{},"KR:111111":{}}'
    elif case in {"nan", "infinity", "overflow"}:
        env["PERIOD_DOCUMENTS"] = "[" + {"nan": "NaN", "infinity": "Infinity", "overflow": "1e400"}[case] + "]"
    elif case == "docs-size":
        env["PERIOD_DOCUMENTS"] = '["' + "가" * 27_000 + '"]'
    elif case == "padded-docs-size":
        env["PERIOD_DOCUMENTS"] = " " * 80_000 + env["PERIOD_DOCUMENTS"]
    elif case == "registry-size":
        env["PERIOD_REGISTRY"] = '{"x":"' + "가" * 86_000 + '"}'
    save()
    if case == "artifact-hash":
        env["ARTIFACT_SHA256"] = "b" * 64
    elif case == "prior-hash":
        env["REPLACE_SHA256"] = "invalid"
    transport = Transport(archive)
    with pytest.raises((ValueError, KeyError, TypeError)):
        namespace["prepare"](env, opener=transport)
    assert env.key_reads == 0 and transport.calls == []
    assert not Path(env["GITHUB_ENV"]).exists() and not list(Path(env["RUNNER_TEMP"]).iterdir())


def test_missing_key_fails_without_transport(prepared):
    namespace, env, _, _, archive, _ = prepared
    env["DART_API_KEY"] = ""
    transport = Transport(archive)
    with pytest.raises(ValueError):
        namespace["prepare"](env, opener=transport)
    assert env.key_reads == 1 and transport.calls == []
    assert not Path(env["GITHUB_ENV"]).exists() and not list(Path(env["RUNNER_TEMP"]).iterdir())


@pytest.mark.parametrize("body", ['{"inputs":{},"inputs":{}}', '{"inputs":NaN}',
                                  '{"inputs":{"period_documents":null}}', " " * 1_000_001])
def test_dispatch_file_rejected_before_key(prepared, body):
    namespace, env, _, _, archive, _ = prepared
    Path(env["GITHUB_EVENT_PATH"]).write_text(body, encoding="utf-8")
    transport = Transport(archive)
    with pytest.raises(ValueError):
        namespace["prepare"](env, opener=transport)
    assert env.key_reads == 0 and transport.calls == []
    assert not Path(env["GITHUB_ENV"]).exists() and not list(Path(env["RUNNER_TEMP"]).iterdir())


@pytest.mark.parametrize("case", ["redirect", "status", "length", "oversized-length", "oversized-body",
                                      "tampered", "not-zip", "timeout"])
def test_transport_failures_have_no_retry_or_publication_paths(prepared, case, monkeypatch, capsys):
    namespace, env, _, _, archive, _ = prepared
    options = {"redirect": {"redirected": True}, "status": {"status": 302},
               "length": {"length": "invalid"}, "oversized-length": {"length": str(4 * 1024 * 1024 + 1)},
               "timeout": {"error": True}}.get(case, {})
    body = {"oversized-body": b"PK\x03\x04" + b"x" * (4 * 1024 * 1024),
            "tampered": archive + b"x", "not-zip": b"<ERROR>secret raw response</ERROR>"}.get(case, archive)
    transport = Transport(body, **options)
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: transport)
    monkeypatch.setattr(namespace["os"], "environ", env)
    with pytest.raises(SystemExit) as error:
        exec(compile(_code(), str(WORKFLOW), "exec"), {"__name__": "__main__"})
    assert str(error.value) == "public-period-preparation-rejected"
    assert len(transport.calls) == 1 and not Path(env["GITHUB_ENV"]).exists()
    assert capsys.readouterr() == ("", "")


def test_no_redirect_handler_and_exclusive_zip(prepared, monkeypatch):
    namespace, env, _, _, archive, _ = prepared
    with pytest.raises(ValueError):
        namespace["NoRedirect"]().redirect_request(None, None, 302, KEY, {}, "https://invalid.example/")
    fixed = Path(env["RUNNER_TEMP"]) / "already-exists"
    fixed.mkdir()
    original = fixed / "dart-document-20260330000218.zip"
    original.write_bytes(b"existing-public-bytes")
    monkeypatch.setattr(namespace["tempfile"], "mkdtemp", lambda **kwargs: str(fixed))
    with pytest.raises(FileExistsError):
        namespace["prepare"](env, opener=Transport(archive))
    assert original.read_bytes() == b"existing-public-bytes" and not Path(env["GITHUB_ENV"]).exists()


def test_workflow_seven_axes_and_unchanged_jobs():
    text = WORKFLOW.read_text(encoding="utf-8")
    prefix = text.split("jobs:\n", 1)[0]
    prefix = re.sub(r"      period_documents:\n.*?(?=      limit:\n)", "", prefix, flags=re.S)
    assert sha256(prefix.encode()).hexdigest() == "8520fbe7b0fbe65cb0b202a0b2ba1cda3c85b52c0a243e264c5383f9e56f0137"
    judge = text.split("  judge:\n", 1)[1].split("  publish-reviewed:\n", 1)[0]
    contracts = text.split("  publish-contracts:\n", 1)[1]
    assert sha256(judge.encode()).hexdigest() == "67e36882b51dce26c6aeaa86c0934b4694191a73528006c74bbdf42e4b622653"
    assert sha256(contracts.encode()).hexdigest() == "e7ac89cf48931c2377ed3eadd7786b8f8b4649d03791e616cb76d4fdfe8af5a4"
    workflow = _workflow()
    publish = workflow["jobs"]["publish-reviewed"]
    assert publish["if"] == "github.event_name == 'workflow_dispatch' && inputs.mode == 'publish-reviewed'"
    steps = publish["steps"]
    prep = next(s for s in steps if s.get("name") == "공개 보고기간 원문 준비")
    assert prep["env"]["DART_API_KEY"] == "${{ secrets.DART_API_KEY }}"
    assert set(prep["env"]) == {"DART_API_KEY", "ARTIFACT_SHA256", "REPLACE_SHA256"}
    assert "GITHUB_EVENT_PATH" in prep["run"]
    assert "inputs.period_documents" not in text and "inputs.period_registry" not in text
    assert all("DART_API_KEY" not in s.get("env", {}) for s in steps if s is not prep)
    assert "OPENAI" not in str(publish) and "SUPABASE" not in str(publish) and "KIS" not in str(publish)
    assert "${{" not in prep["run"] and "print(" not in prep["run"]
    assert "ProxyHandler({})" in prep["run"] and "NoRedirect()" in prep["run"]
    publishers = [s["run"] for s in steps if "upload-ai-candidates.cjs" in s.get("run", "")]
    assert len(publishers) == 2 and publishers[0].split("node scripts/", 1)[0] == publishers[1].split("NODE_PATH=", 1)[0]
    assert all('"${period_args[@]}"' in run for run in publishers)
    assert all(flag in publishers[0] for flag in ("--period-input", "--period-source-dir", "--issuer-registry-path"))
    assert steps.index(prep) < next(i for i, s in enumerate(steps) if "upload-ai-candidates.cjs" in s.get("run", ""))
    assert "actions/upload-artifact" not in text and "actions/cache" not in text and "git commit" not in text
    assert len([s for s in steps if s.get("run", "").startswith("python3 -m pip install")]) == 1
    # 실제 manual 게시/다음 scheduled 수락은 MAIN이 별도 확인한다. 여기서는 실행하지 않는다.


def test_changed_publish_shell_syntax_only():
    for step in _workflow()["jobs"]["publish-reviewed"]["steps"]:
        if "run" in step:
            result = subprocess.run(["bash", "-n"], input=step["run"], text=True, capture_output=True)
            assert result.returncode == 0, step.get("name")
