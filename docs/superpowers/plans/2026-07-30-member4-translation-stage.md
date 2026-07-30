# Member 4 M1 Translation Stage Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic language detection, a replaceable translation boundary, and a real `translate` task stage without downloading or claiming success for an unapproved model.

**Architecture:** `worker/adapters/translation.py` defines the provider-neutral interface; `worker/stages/translate.py` owns language classification and immutable transcript transformation. `worker/pipeline.py` persists the ASR transcript, advances to translate, applies the adapter only to English/mixed segments, and writes the same existing transcript contract again with aligned translations.

**Tech Stack:** Python 3.13, Pydantic transcript contracts, pytest 9.1, existing Worker state and HTTP transcript endpoint.

## Global Constraints

- Do not add a translation backend endpoint or modify transcript Schema.
- Do not download model weights or add a real model dependency until the group leader confirms model revision, license, size, and runtime requirements.
- Preserve every segment’s original `text`, `index`, `start_ms`, `end_ms`, and `speaker`.
- Chinese-only input must complete translate without invoking an adapter.
- Test translations must be visibly fake and must never be recorded as real validation.
- Do not modify backend implementation, generic Agent files, or Agent runner.
- Do not commit media, full transcripts, models, caches, `.agents/`, or `skills-lock.json`.

---

## File Structure

- Modify `worker/types.py`: translation batch result types and translated count in `PipelineResult`.
- Replace `worker/adapters/translation.py`: protocol only; no model import.
- Replace `worker/stages/translate.py`: language detection and transcript transformation.
- Modify `worker/errors.py`: stable translation errors.
- Modify `worker/pipeline.py`: real translate stage and existing transcript writeback.
- Modify `worker/runner.py`: optional adapter injection without selecting a real provider.
- Create `tests/unit/test_worker_translation.py`: language, alignment, stop, and error tests.
- Modify `tests/unit/test_worker.py`: pipeline state and writeback tests.
- Modify `worker/media-worker-guide.md`: honest model gate and stage behavior.

### Task 1: Translation Types and Adapter Protocol

**Files:**
- Modify: `worker/types.py`
- Replace: `worker/adapters/translation.py`
- Create: `tests/unit/test_worker_translation.py`

**Interfaces:**
- Produces: `TranslationBatch`, `TranslationAdapter.translate_batch(...)`, and `DetectedLanguage`.
- Consumes: plain strings only; no database or task objects cross the adapter boundary.

- [ ] **Step 1: Write the failing adapter-contract test**

```python
class FakeTranslationAdapter:
    model_name = "fake-translation-for-tests"

    def translate_batch(
        self,
        texts: tuple[str, ...],
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationBatch:
        return TranslationBatch(
            translations=tuple(f"[测试译文]{text}" for text in texts),
            model_name=self.model_name,
        )


def test_translation_adapter_preserves_batch_order() -> None:
    result = FakeTranslationAdapter().translate_batch(
        ("first", "second"), source_language="en", target_language="zh"
    )
    assert result.translations == ("[测试译文]first", "[测试译文]second")
```

- [ ] **Step 2: Verify the test fails**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_translation.py -q`
Expected: FAIL because `TranslationBatch` and `TranslationAdapter` do not exist.

- [ ] **Step 3: Define focused types**

```python
class DetectedLanguage(StrEnum):
    ZH = "zh"
    EN = "en"
    MIXED = "en-zh"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class TranslationBatch:
    translations: tuple[str, ...]
    model_name: str
```

```python
class TranslationAdapter(Protocol):
    model_name: str

    def translate_batch(
        self,
        texts: tuple[str, ...],
        *,
        source_language: str,
        target_language: str,
    ) -> TranslationBatch: ...
```

- [ ] **Step 4: Run the adapter test**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_translation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit the adapter boundary**

```bash
git add worker/types.py worker/adapters/translation.py tests/unit/test_worker_translation.py
git commit -m "feat(worker): define translation adapter contract"
```

### Task 2: Language Detection and Immutable Translation

**Files:**
- Replace: `worker/stages/translate.py`
- Modify: `tests/unit/test_worker_translation.py`

**Interfaces:**
- Produces: `detect_language(text: str) -> DetectedLanguage`.
- Produces: `translate_transcript(transcript, adapter, stop_event=None) -> InternalTranscriptWrite`.

- [ ] **Step 1: Write language classification tests**

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("这是中文课堂。", DetectedLanguage.ZH),
        ("This is an AI lecture.", DetectedLanguage.EN),
        ("我们使用 Transformer model。", DetectedLanguage.MIXED),
        ("1234…", DetectedLanguage.OTHER),
    ],
)
def test_detect_language(text: str, expected: DetectedLanguage) -> None:
    assert detect_language(text) is expected
```

- [ ] **Step 2: Implement deterministic Unicode detection**

Use compiled regular expressions for CJK Unified Ideographs and ASCII Latin letters. Presence of both is `MIXED`; CJK only is `ZH`; Latin only is `EN`; neither is `OTHER`. Do not call a statistical language model.

- [ ] **Step 3: Write transcript transformation tests**

Build an `InternalTranscriptWrite` containing Chinese, English, and mixed segments. Assert:

```python
assert translated.segments[0].translation is None
assert translated.segments[1].translation == "[测试译文]Explain the model."
assert translated.segments[2].translation == "[测试译文]这是 Transformer architecture."
assert [s.text for s in translated.segments] == [s.text for s in original.segments]
assert translated.translation_language == "zh"
```

Also assert the fake adapter receives only the English and mixed texts in their original order.

- [ ] **Step 4: Implement immutable translation**

Use `segment.model_copy(update={"translation": value})`; never rebuild timestamps from floats. If there are no English/mixed segments, return a validated copy with no adapter call. If adapter is absent and translation is required, raise `TRANSLATION_UNAVAILABLE`.

- [ ] **Step 5: Add fail-closed tests**

Cover:

- adapter output count differs from request count;
- adapter returns empty/whitespace translation;
- unsupported `OTHER` segment in a task requiring bilingual output;
- stop event set before and after adapter call;
- adapter exception is mapped without exposing input text.

- [ ] **Step 6: Run translation-stage tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker_translation.py -q`
Expected: PASS.

- [ ] **Step 7: Commit language and translation stage**

```bash
git add worker/stages/translate.py tests/unit/test_worker_translation.py
git commit -m "feat(worker): translate English transcript segments"
```

### Task 3: Stable Translation Errors

**Files:**
- Modify: `worker/errors.py`
- Modify: `tests/unit/test_worker.py`
- Modify: `tests/unit/test_worker_translation.py`

**Interfaces:**
- Produces: `TRANSLATION_UNAVAILABLE`, `TRANSLATION_TIMEOUT`, `TRANSLATION_SCHEMA_INVALID`, and `UNSUPPORTED_LANGUAGE`.

- [ ] **Step 1: Extend the exact error-code assertion**

Add the four values to `test_worker_error_codes_match_media_design`.

- [ ] **Step 2: Add public-message privacy tests**

For each new code, assert `public_worker_error_message(code)` contains no input text, path, URL, or provider exception.

- [ ] **Step 3: Implement mappings**

Map unavailable/timeout to platform `UPSTREAM_UNAVAILABLE`; schema and unsupported language to platform `VALIDATION_ERROR`. Add stable Chinese public messages to `_PUBLIC_MESSAGES`.

- [ ] **Step 4: Run error tests**

Run: `.venv/bin/python -m pytest tests/unit/test_worker.py tests/unit/test_worker_translation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit error contracts**

```bash
git add worker/errors.py tests/unit/test_worker.py tests/unit/test_worker_translation.py
git commit -m "feat(worker): add stable translation failures"
```

### Task 4: Translate Stage in the Media Pipeline

**Files:**
- Modify: `worker/pipeline.py`
- Modify: `worker/types.py`
- Modify: `worker/runner.py`
- Modify: `tests/unit/test_worker.py`

**Interfaces:**
- Consumes: `translate_transcript` and optional `TranslationAdapter`.
- Produces: task events `translate/running/0.0` then `translate/running/1.0`; returns `PipelineResult.translated_segments`.

- [ ] **Step 1: Write a failing pipeline test**

Run a short fake ASR result with one English segment and a fake adapter. Assert:

```python
assert [event.stage for event in store.events[task.task_id]][-2:] == [
    TaskStage.TRANSLATE,
    TaskStage.TRANSLATE,
]
assert store.transcripts[task.task_id].segments[0].text == "Explain AI."
assert store.transcripts[task.task_id].segments[0].translation == "[测试译文]Explain AI."
assert result.translated_segments == 1
```

Also assert `save_transcript` receives the original ASR batch before translate and the translated batch after translate by using a recording store.

- [ ] **Step 2: Verify the test fails**

Run: `.venv/bin/python -m pytest tests/unit/test_worker.py -k "translate_stage" -q`
Expected: FAIL because the pipeline ends at transcribe.

- [ ] **Step 3: Add the translate stage**

Extend `run_pipeline(..., translation_adapter: TranslationAdapter | None = None)`.
After the first transcript write:

1. write `TaskStage.TRANSLATE / RUNNING / 0.0`;
2. call `translate_transcript`;
3. check stop;
4. write the translated transcript through the same `JobStore.save_transcript`;
5. write `TaskStage.TRANSLATE / RUNNING / 1.0`.

Track `current_stage=TRANSLATE` so failures report the correct stage.

- [ ] **Step 4: Keep CLI behavior honest**

The local and remote runner pass `translation_adapter=None` until a model is approved. Chinese-only transcripts pass; English/mixed transcripts fail with `TRANSLATION_UNAVAILABLE`. Do not silently use the test adapter outside tests.

- [ ] **Step 5: Run Worker regression**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_worker.py tests/unit/test_worker_translation.py -q
.venv/bin/python -m ruff check worker tests/unit/test_worker.py tests/unit/test_worker_translation.py
```

Expected: PASS.

- [ ] **Step 6: Commit pipeline integration**

```bash
git add worker/pipeline.py worker/types.py worker/runner.py tests/unit/test_worker.py
git commit -m "feat(worker): persist aligned translate stage"
```

### Task 5: Translation Documentation Without False Validation

**Files:**
- Modify: `worker/media-worker-guide.md`
- Modify: `reports/contributions/member-4.md`
- Modify: `docs/ai-collaboration-log.md`

**Interfaces:**
- Produces: a truthful handoff stating adapter/stage tests are complete and real model validation is still gated.

- [ ] **Step 1: Document behavior and gate**

Record:

- original text is never overwritten;
- Chinese-only input skips model invocation;
- English/mixed input requires a configured real adapter;
- the fake adapter is test-only;
- no model has been downloaded or validated;
- candidate metadata requires manual confirmation.

- [ ] **Step 2: Run static checks**

Run:

```bash
.venv/bin/python -m pytest tests/unit/test_worker.py tests/unit/test_worker_translation.py -q
.venv/bin/python -m ruff check worker tests/unit/test_worker.py tests/unit/test_worker_translation.py
git diff --check
```

Expected: PASS.

- [ ] **Step 3: Commit documentation**

```bash
git add worker/media-worker-guide.md reports/contributions/member-4.md docs/ai-collaboration-log.md
git commit -m "docs(worker): record translation stage boundary"
```
