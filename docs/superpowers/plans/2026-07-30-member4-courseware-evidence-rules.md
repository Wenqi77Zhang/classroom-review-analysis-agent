# Member 4 M1 Courseware, Evidence, and Domain Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse PDF/PPTX text and page numbers, build a validated in-memory evidence draft, provide specialist AI/humanities rules, and hand member 3 an explicit backend contract proposal without implementing backend persistence.

**Architecture:** Courseware parsing is isolated behind a content-type dispatcher; evidence construction emits existing `agent.contracts.EvidenceItem` objects with deterministic IDs and frozen `EvidenceReference` locators. Domain Skill files and a pure professional gate are implemented without modifying the orchestrator. A non-frozen proposal document defines the backend guarantees member 3 must implement before integration.

**Tech Stack:** Python 3.13, `pypdf` 6.x, `python-pptx` 1.x, Pydantic v2, pytest 9.1, dev-only ReportLab 5.x for generated PDF fixtures, existing Agent and backend evidence contracts.

## Global Constraints

- P0 parses text and one-based page numbers only; PNG rendering and derived uploads remain P1.
- Add `pypdf>=6.14,<7.0` and `python-pptx>=1.0,<2.0` only to the Worker optional dependency group.
- Add `reportlab>=5.0,<6.0` only to the dev dependency group so tests can generate text-bearing PDFs at runtime; Worker production does not import it.
- Do not create backend tables, migrations, routes, repositories, or permission code.
- Do not modify `agent/orchestrator.py`, `agent/skills/common.py`, generic retrieval, Provider routing, or Agent runner.
- Evidence without a real time/page locator must fail; never invent `image_ref`.
- Runtime-generated test files must be synthetic; do not commit third-party courseware binaries.
- Do not commit media, full transcripts, model files, `.agents/`, or `skills-lock.json`.

---

## File Structure

- Modify `pyproject.toml`: Worker-only parser dependencies.
- Create `worker/courseware_types.py`: immutable page/document structures.
- Replace `worker/stages/parse_courseware.py`: PDF/PPTX parser and limits.
- Replace `worker/stages/build_evidence_index.py`: deterministic evidence draft builder.
- Modify `worker/errors.py`: courseware/evidence stable codes.
- Replace `agent/skills/computer_ai.py`: specialist `SkillSpec`.
- Replace `agent/skills/humanities.py`: specialist `SkillSpec`.
- Replace `agent/validators/evidence_gate.py`: pure professional evidence checks.
- Create `tests/unit/test_worker_courseware.py`: generated PDF/PPTX tests.
- Create `tests/unit/test_worker_evidence.py`: evidence builder tests.
- Create `tests/unit/test_member4_domain_rules.py`: rules and gate tests without orchestrator changes.
- Create `worker/m1-backend-contract-proposal.md`: non-frozen member 3 handoff.
- Modify `worker/media-worker-guide.md`: P0 courseware/evidence boundary.

### Task 1: Worker-Only Parser Dependencies and Types

**Files:**
- Modify: `pyproject.toml`
- Create: `worker/courseware_types.py`
- Create: `tests/unit/test_worker_courseware.py`

**Interfaces:**
- Produces: `CoursewarePage` and `CoursewareDocument`.

- [ ] **Step 1: Add failing immutable-type tests**

```python
def test_courseware_types_use_one_based_pages() -> None:
    with pytest.raises(ValueError):
        CoursewarePage(page_no=0, text="invalid")
    page = CoursewarePage(page_no=1, text="Introduction")
    document = CoursewareDocument(asset_id=uuid4(), pages=(page,))
    assert document.pages[0].page_no == 1
```

- [ ] **Step 2: Implement immutable types**

```python
@dataclass(frozen=True, slots=True)
class CoursewarePage:
    page_no: int
    text: str

    def __post_init__(self) -> None:
        if self.page_no < 1:
            raise ValueError("page_no must be one-based")


@dataclass(frozen=True, slots=True)
class CoursewareDocument:
    asset_id: UUID
    pages: tuple[CoursewarePage, ...]
```

- [ ] **Step 3: Add parser dependencies**

In `[project.optional-dependencies].worker`, add:

```toml
"pypdf>=6.14,<7.0",
"python-pptx>=1.0,<2.0",
```

In `[project.optional-dependencies].dev`, add:

```toml
"reportlab>=5.0,<6.0",
```

ReportLab is test-only. No binary fixture is committed.

- [ ] **Step 4: Install declared Worker dependencies**

Run: `.venv/bin/python -m pip install -e ".[dev,worker]"`
Expected: successful resolution under Python 3.13.

- [ ] **Step 5: Run the type test**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_courseware.py -q`
Expected: PASS.

- [ ] **Step 6: Commit dependencies and types**

```bash
git add pyproject.toml worker/courseware_types.py tests/unit/test_worker_courseware.py
git commit -m "feat(worker): define courseware page types"
```

### Task 2: PDF/PPTX Text and Page Parsing

**Files:**
- Replace: `worker/stages/parse_courseware.py`
- Modify: `worker/errors.py`
- Modify: `tests/unit/test_worker_courseware.py`

**Interfaces:**
- Produces: `parse_courseware(path, *, asset_id, content_type, max_pages=500) -> CoursewareDocument`.

- [ ] **Step 1: Generate test inputs at runtime**

Use this concrete helper for the text-bearing PDF:

```python
from reportlab.pdfgen import canvas


def _write_pdf(path: Path) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 720, "Artificial intelligence")
    document.showPage()
    document.drawString(72, 720, "Machine learning")
    document.save()
```

Use `Presentation()` for a two-slide PPTX. On slide 1, add a title containing
`"Algorithm"`, a one-cell table containing `"Complexity"`, and notes text
`"Instructor note"`. On slide 2, add a title containing `"Humanities"`. Save both
documents under pytest's `tmp_path`, so no generated binary enters Git.

- [ ] **Step 2: Write failing success tests**

Assert:

```python
assert [page.page_no for page in pdf.pages] == [1, 2]
assert "Artificial intelligence" in pdf.pages[0].text
assert [page.page_no for page in pptx.pages] == [1, 2]
assert "Algorithm" in pptx.pages[0].text
assert "Complexity" in pptx.pages[0].text
```

- [ ] **Step 3: Implement content-type dispatch**

Supported types:

- `application/pdf`
- `application/vnd.openxmlformats-officedocument.presentationml.presentation`

Reject every other type with `COURSEWARE_UNSUPPORTED`. Do not trust filename suffixes because B2 downloads use generated local names.

- [ ] **Step 4: Implement PDF parsing**

Use `PdfReader`. Reject encrypted documents, more than `max_pages`, parse exceptions, and zero-page files. Normalize extracted text by joining non-empty lines with single newlines; preserve empty pages as `text=""`.

- [ ] **Step 5: Implement PPTX parsing**

Use `Presentation`. For each slide, collect text-frame paragraphs, table-cell text, and existing notes text in stable shape order. Do not create notes slides during reading. Enforce `max_pages`.

- [ ] **Step 6: Add failure and privacy tests**

Cover unsupported MIME, encrypted/broken PDF, broken PPTX, page limit, and an exception containing a sensitive absolute path. Assert the raised public message does not contain the path.

- [ ] **Step 7: Add stable error codes**

Add `COURSEWARE_UNSUPPORTED` and `COURSEWARE_PARSE_FAILED`. Map unsupported to `VALIDATION_ERROR` and parse failure to `UPSTREAM_UNAVAILABLE`; add stable public messages.

- [ ] **Step 8: Run parser tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_courseware.py -q`
Expected: PASS.

- [ ] **Step 9: Commit parser**

```bash
git add worker/stages/parse_courseware.py worker/errors.py tests/unit/test_worker_courseware.py
git commit -m "feat(worker): parse PDF and PPTX courseware"
```

### Task 3: Deterministic Evidence Draft

**Files:**
- Replace: `worker/stages/build_evidence_index.py`
- Modify: `worker/errors.py`
- Create: `tests/unit/test_worker_evidence.py`

**Interfaces:**
- Produces:

```python
build_evidence_index(
    *,
    task_id: UUID,
    owner_id: UUID,
    video_asset_id: UUID,
    transcript: InternalTranscriptWrite,
    courseware: Sequence[CoursewareDocument] = (),
) -> tuple[EvidenceItem, ...]
```

- [ ] **Step 1: Write transcript/video evidence tests**

For two transcript segments, assert the result contains one `VIDEO` item and one `TRANSCRIPT` item per segment. Every item must preserve the exact integer range and original/translation text.

- [ ] **Step 2: Write courseware evidence tests**

For two courseware pages, assert one `COURSEWARE` item per non-empty page with the original asset ID and one-based page number. Empty pages are omitted because they contain no quotable evidence.

- [ ] **Step 3: Implement deterministic IDs**

Use a module-owned UUID namespace and:

```python
name = "|".join(
    [str(task_id), source_type.value, str(asset_id or ""), locator, sha256(text.encode()).hexdigest()]
)
evidence_id = uuid5(EVIDENCE_NAMESPACE, name)
```

The locator is `start_ms:end_ms` or `page_no`. Never include the full text in metadata.

- [ ] **Step 4: Build frozen references**

Construct `EvidenceReference` directly so Pydantic enforces locators. Use `quote=text[:2000]`, `text` as the full evidence item value, and only these metadata keys:

```python
{"pipeline_version": "worker-evidence-v1", "source_index": segment.index}
```

Do not synthesize transcript segment IDs before backend persistence returns real IDs.

- [ ] **Step 5: Add fail-closed tests**

Cover empty transcript, invalid cross-duration range, duplicate page numbers, missing video asset ID, and an item exceeding Pydantic limits. Assert `EVIDENCE_INDEX_INVALID`.

- [ ] **Step 6: Run evidence tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_evidence.py -q`
Expected: PASS.

- [ ] **Step 7: Commit evidence generation**

```bash
git add worker/stages/build_evidence_index.py worker/errors.py tests/unit/test_worker_evidence.py
git commit -m "feat(worker): build deterministic evidence drafts"
```

### Task 4: Computer/AI and Humanities Skill Rules

**Files:**
- Replace: `agent/skills/computer_ai.py`
- Replace: `agent/skills/humanities.py`
- Create: `tests/unit/test_member4_domain_rules.py`

**Interfaces:**
- Produces: `get_computer_ai_skill() -> SkillSpec` and `get_humanities_skill() -> SkillSpec`.
- Does not register the skills in the orchestrator; member 5 owns registration.

- [ ] **Step 1: Write failing SkillSpec tests**

```python
def test_member4_skills_have_stable_names_and_versions() -> None:
    computer = get_computer_ai_skill()
    humanities = get_humanities_skill()
    assert (computer.name, computer.version) == ("computer_ai", "1.0.0")
    assert (humanities.name, humanities.version) == ("humanities", "1.0.0")
```

Assert computer instructions mention code/demo evidence and prohibit inferring student mastery. Assert humanities instructions require original/courseware evidence and prohibit inferring position, motivation, emotion, or identity.

- [ ] **Step 2: Implement immutable SkillSpec constants and copy-returning getters**

Follow `agent/skills/common.py`; getters return `model_copy(deep=True)`.

- [ ] **Step 3: Verify common Skill is unchanged**

Add this exact regression assertion:

```python
assert get_common_skill().model_dump() == {
    "name": "common",
    "version": "1.0.0",
    "instructions": (
        "分析课堂结构、目标衔接、讲解清晰度、提问与等待、例证和总结。"
        "事实只描述证据可观察内容；判断必须说明事实与标准的关系；"
        "建议必须可操作且不得超出已有证据。每条结论至少引用一个给定证据 ID。"
    ),
}
```

- [ ] **Step 4: Run domain rule tests**

Run: `.venv/bin/python -m pytest tests/unit/test_member4_domain_rules.py tests/unit/test_agent.py -q`
Expected: PASS.

- [ ] **Step 5: Commit Skill rules**

```bash
git add agent/skills/computer_ai.py agent/skills/humanities.py tests/unit/test_member4_domain_rules.py
git commit -m "feat(agent): add member4 domain skill rules"
```

### Task 5: Pure Professional Evidence Gate

**Files:**
- Replace: `agent/validators/evidence_gate.py`
- Modify: `tests/unit/test_member4_domain_rules.py`

**Interfaces:**
- Produces:

```python
validate_computer_ai_evidence(
    evidence: Sequence[EvidenceItem],
    *,
    requires_visual_proof: bool,
    bilingual_required: bool,
) -> None

validate_humanities_evidence(
    evidence: Sequence[EvidenceItem],
    *,
    bilingual_required: bool,
) -> None
```

- [ ] **Step 1: Write positive and negative examples**

Computer/AI:

- transcript evidence passes for a concept explanation;
- `requires_visual_proof=True` rejects transcript-only input;
- video/frame/courseware evidence passes visual proof.

Humanities:

- transcript with non-empty original text passes;
- courseware with page number passes;
- video-only evidence without a quoted original fails.

Both domains reject missing translation when `bilingual_required=True`.

- [ ] **Step 2: Implement a dedicated exception**

```python
class ProfessionalEvidenceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
```

Use fixed codes `PROFESSIONAL_EVIDENCE_MISSING`, `VISUAL_EVIDENCE_REQUIRED`,
`ORIGINAL_TEXT_REQUIRED`, and `PROFESSIONAL_TRANSLATION_REQUIRED`.

- [ ] **Step 3: Implement pure validators**

The validators inspect only `EvidenceItem` and frozen source types. They do not call a model, modify an Agent state, or import `AgentOrchestrator`.

- [ ] **Step 4: Prove no generic integration changed**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_member4_domain_rules.py tests/unit/test_agent.py -q
git diff -- agent/orchestrator.py agent/skills/common.py agent/tools/retrieve_evidence.py
```

Expected: tests pass; the diff command prints nothing.

- [ ] **Step 5: Commit professional gate**

```bash
git add agent/validators/evidence_gate.py tests/unit/test_member4_domain_rules.py
git commit -m "feat(agent): add professional evidence rules"
```

### Task 6: Member 3 Contract Proposal

**Files:**
- Create: `worker/m1-backend-contract-proposal.md`

**Interfaces:**
- Produces a review artifact only; it does not freeze Schema or authorize backend implementation by member 4.

- [ ] **Step 1: Write the proposal with exact invariants**

Include:

1. valid Worker lease required for transcript/evidence writes;
2. handoff makes evidence immutable to Worker;
3. evidence replacement is versioned or audited;
4. evidence referenced by Agent conclusions cannot silently disappear;
5. retry after any transcript-dependent failure explicitly resets to `transcribe / queued` and appends old/new stage event data;
6. handoff atomically checks evidence and bilingual completeness before `analyze / queued`;
7. owner/task isolation and 404 cross-owner behavior;
8. single-Worker limitation until `lease_id` is frozen.

Mark every proposed route and field as “proposal—not frozen; member 3 owns implementation.”

- [ ] **Step 2: Add acceptance cases**

Provide request/response shapes as non-authoritative examples and a table of expected outcomes for valid lease, expired lease, post-handoff overwrite, retry stage reset, version conflict, and referenced evidence deletion.

- [ ] **Step 3: Verify no backend code changed**

Run: `git diff -- backend`
Expected: no output.

- [ ] **Step 4: Commit the proposal**

```bash
git add worker/m1-backend-contract-proposal.md
git commit -m "docs(worker): propose M1 evidence handoff contract"
```

### Task 7: Stage-One Verification and Handoff Documentation

**Files:**
- Modify: `worker/media-worker-guide.md`
- Modify: `agent/agent-module-guide.md`
- Modify: `reports/contributions/member-4.md`
- Modify: `docs/ai-collaboration-log.md`

**Interfaces:**
- Produces a truthful stage-one handoff to members 3 and 5.

- [ ] **Step 1: Document completed and blocked boundaries**

Record exactly:

- PDF/PPTX text/page parser status;
- evidence draft status;
- professional Skill/gate status;
- no backend persistence/handoff yet;
- no real model validation yet;
- PNG rendering remains P1;
- member 3 and member 5 review requests.

- [ ] **Step 2: Run stage-one regression**

Run:

```bash
.venv/bin/python -m pytest \
  tests/unit/test_worker.py \
  tests/unit/test_worker_runtime.py \
  tests/unit/test_worker_translation.py \
  tests/unit/test_worker_courseware.py \
  tests/unit/test_worker_evidence.py \
  tests/unit/test_member4_domain_rules.py \
  tests/unit/test_agent.py -q
.venv/bin/python -m ruff check worker agent tests/unit
git diff --check
```

Expected: all commands pass.

- [ ] **Step 3: Run the full repository gates**

Run:

```bash
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Expected: all configured tests pass; environment-dependent tests may skip only under their existing explicit conditions.

- [ ] **Step 4: Commit handoff documentation**

```bash
git add \
  worker/media-worker-guide.md \
  agent/agent-module-guide.md \
  reports/contributions/member-4.md \
  docs/ai-collaboration-log.md
git commit -m "docs(worker): hand off M1 stage-one contracts"
```
