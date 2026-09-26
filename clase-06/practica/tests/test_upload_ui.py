import pathlib


INDEX_HTML = (
    pathlib.Path(__file__).resolve().parents[1] / "api" / "static" / "index.html"
).read_text(encoding="utf-8")


def test_upload_controls_and_limits_are_explicit_and_accessible() -> None:
    html = INDEX_HTML

    assert html.index('id="upload-title"') < html.index('id="query-title"')
    assert '<form id="upload-form">' in html
    assert 'id="pdf-file" name="pdf" type="file"' in html
    assert 'accept=".pdf,application/pdf"' in html
    assert "10 MiB" in html and "10485760" in html
    assert all(limit in html for limit in ("20 páginas", "200.000 caracteres", "120 fragmentos"))
    assert "MAX_PAGE_CHARS=20000" in html
    assert "20.000 caracteres extraídos por página" in html
    assert "sólo texto" in html and "OCR" in html and "cifrados" in html
    assert "fetch('/api/documents'" in html
    assert "body: file" in html
    assert "'Content-Type': 'application/pdf'" in html
    assert "'X-Document-Title': encodeURIComponent(file.name)" in html
    assert all(str(status) in html for status in (422, 413, 503, 429))


def test_catalog_inspection_and_query_filter_are_rendered_safely() -> None:
    html = INDEX_HTML

    assert '<select id="document-id" name="document_id">' in html
    assert "Todos los documentos" in html
    assert "encodeURIComponent(documentId)" in html
    assert "chunk_index" in html
    assert "content_sha256" in html
    assert "vector_dims" in html
    assert "embedding_preview" in html
    assert "requestBody.document_id = selectedDocument" in html
    assert "queryMode !== 'text-to-sql'" in html
    assert "lab_read" in html
    assert ".textContent" in html
    assert "document.createElement" in html
    assert "innerHTML" not in html
    assert "eval(" not in html


def test_upload_summary_sources_and_privacy_contract_are_visible() -> None:
    html = INDEX_HTML

    for field in (
        "document_id",
        "title",
        "sha256",
        "object_key",
        "page_count",
        "chunk_count",
        "embedding_model",
        "dimension",
        "index_status",
        "embedding_preview",
    ):
        assert field in html
    assert "PDF almacenado" in html
    assert "Fragmentos generados" in html
    assert "Embeddings indexados" in html
    assert "cosine_distance" in html
    assert "locales" in html
    assert "fragmentos recuperados del PDF" in html
    assert "OpenRouter" in html
    assert "corte de evidencia es aproximado" in html
    assert "0,20" in html and "manual inicial" in html and "no es universal" in html
    assert "S3" not in html or "navegador" in html


def test_catalog_and_inspection_discard_stale_async_responses() -> None:
    html = INDEX_HTML

    assert "let catalogRequestGeneration = 0" in html
    assert "let inspectRequestGeneration = 0" in html
    assert "const requestGeneration = ++catalogRequestGeneration" in html
    assert "const requestGeneration = ++inspectRequestGeneration" in html
    assert "requestGeneration !== catalogRequestGeneration" in html
    assert "requestGeneration !== inspectRequestGeneration" in html
    catalog_start = html.index("async function loadDocuments")
    catalog_end = html.index("function renderDocumentDetails", catalog_start)
    catalog_source = html[catalog_start:catalog_end]
    inspect_start = html.index("async function inspectDocument")
    inspect_end = html.index("uploadForm.addEventListener", inspect_start)
    inspect_source = html[inspect_start:inspect_end]
    assert catalog_source.index("requestGeneration !== catalogRequestGeneration") < catalog_source.index("renderDocumentList(")
    assert inspect_source.index("requestGeneration !== inspectRequestGeneration") < inspect_source.index("renderDocumentDetails(")


def test_catalog_and_inspection_failures_are_separate_and_report_partial_upload() -> None:
    html = INDEX_HTML

    assert 'id="documents-error"' in html
    assert 'id="inspect-error"' in html
    inspect_start = html.index("async function inspectDocument")
    inspect_end = html.index("uploadForm.addEventListener", inspect_start)
    inspect_source = html[inspect_start:inspect_end]
    assert "#inspect-error" in inspect_source
    assert "#documents-error" not in inspect_source
    assert "document.querySelector('#document-metadata').replaceChildren()" in inspect_source
    assert "document.querySelector('#document-pages').replaceChildren()" in inspect_source
    assert "return true" in inspect_source and "return false" in inspect_source
    assert "const catalogLoaded = await loadDocuments(payload.document_id)" in html
    assert "const documentInspected = await inspectDocument(payload.document_id)" in html
    assert "pero no se pudo actualizar el catálogo" in html
    assert "pero no se pudo completar la inspección" in html
    assert "pero no se pudieron actualizar el catálogo ni la inspección" in html


def test_each_upload_attempt_clears_previous_result_before_client_validation() -> None:
    html = INDEX_HTML

    submit_start = html.index("uploadForm.addEventListener('submit'")
    upload_source = html[submit_start:]
    clear_status = upload_source.index("uploadStatus.textContent = ''")
    clear_result = upload_source.index("document.querySelector('#upload-result').hidden = true")
    read_file = upload_source.index("const file = document.querySelector('#pdf-file').files[0]")
    size_validation = upload_source.index("file.size > MAX_PDF_BYTES")
    type_validation = upload_source.index("const looksLikePdf")
    assert clear_status < read_file
    assert clear_result < read_file
    assert clear_result < size_validation
    assert clear_result < type_validation


def test_existing_free_question_and_optional_examples_remain_intact() -> None:
    html = INDEX_HTML

    assert '<textarea id="question" name="question" required minlength="3" maxlength="500"' in html
    assert 'aria-describedby="question-help"></textarea>' in html
    assert html.count('class="example" type="button"') == 3
    assert "example.addEventListener('click'" in html
    assert "question.focus()" in html
    assert 'id="top-k" name="top_k" type="number" min="1" max="4" value="4"' in html
    assert "fetch('/api/query'" in html
    assert all(marker in html for marker in ('id="sql"', 'id="rows"', 'id="trace"', 'id="sources"'))
    assert "OPENROUTER_API_KEY" not in html
    assert "http://uploader" not in html


def test_query_modes_use_plain_language_labels_and_an_accessible_live_guide() -> None:
    html = INDEX_HTML

    expected_options = (
        '<option value="rag">Consultar documentos (RAG)</option>',
        '<option value="text-to-sql">Consultar telemetría (Text-to-SQL)</option>',
        '<option value="integrated">Combinar telemetría y documentos (Integrado)</option>',
    )
    assert all(option in html for option in expected_options)
    selector_end = html.index("</label>", html.index('<select id="mode"'))
    guide_start = html.index('id="mode-guide"')
    document_label = html.index('<label for="document-id">')
    assert selector_end < guide_start < document_label
    assert 'aria-live="polite"' in html[guide_start : guide_start + 180]
    assert 'aria-atomic="true"' in html[guide_start : guide_start + 180]
    assert 'class="mode-guide"' in html[guide_start - 80 : guide_start + 180]


def test_each_query_mode_has_an_honest_contextual_explanation() -> None:
    html = INDEX_HTML

    assert "E5 local" in html
    assert "página, fragmento y distancia" in html
    assert "sólo si encuentra fragmentos" in html
    assert "OpenRouter genera una consulta SQL" in html
    assert "guard de seguridad" in html
    assert "vistas lab_read con un rol de sólo lectura" in html
    assert "ignora los PDF, el documento elegido y la cantidad de fragmentos" in html
    assert "Primero ejecuta SQL protegido" in html
    assert "después busca con E5" in html
    assert "puede ser una segunda llamada al proveedor" in html
    assert "sin evidencia de PDF no atribuye respaldo al documento" in html
    assert "Cambiar esta selección no envía ninguna consulta" in html
    assert "Sólo Consultar puede contactar a OpenRouter y generar costo" in html
    assert "modeGuide.textContent" in html
    assert "updateQueryModeUI();" in html


def test_examples_choose_explicit_modes_without_submitting_or_fetching() -> None:
    html = INDEX_HTML

    assert html.count('data-mode="rag"') == 1
    assert html.count('data-mode="text-to-sql"') == 1
    assert html.count('data-mode="integrated"') == 1
    assert html.count('data-manual-seed="true"') == 2
    assert "Documentos (manual inicial) · ¿Cómo preparo AIR-002" in html
    assert "Telemetría · ¿Cuál fue el promedio de CO2" in html
    assert "Integrado (mediciones y manual inicial) · ¿Cuál fue el promedio" in html
    assert "topK.disabled = textToSql" in html
    assert "topK.setAttribute('aria-disabled', String(textToSql))" in html
    assert 'const MANUAL_SEED_DOCUMENT_ID = "air-quality-pro-manual"' in html
    assert "mode.value = example.dataset.mode" in html
    assert "updateQueryModeUI(manualHint)" in html
    assert "option.value === MANUAL_SEED_DOCUMENT_ID" in html
    assert "documentSelect.value = MANUAL_SEED_DOCUMENT_ID" in html
    assert "documentSelect.value = ''" in html
    assert "manual inicial no está disponible" in html

    handler_start = html.index("document.querySelectorAll('.example')")
    handler_end = html.index("function setText", handler_start)
    handler = html[handler_start:handler_end]
    assert "fetch(" not in handler
    assert ".submit(" not in handler
    assert "requestSubmit(" not in handler
    assert "submit.click(" not in handler

    change_start = html.index("mode.addEventListener('change'")
    change_end = html.index("function renderSources", change_start)
    change_handler = html[change_start:change_end]
    assert "fetch(" not in change_handler
    assert ".submit(" not in change_handler
    assert "requestSubmit(" not in change_handler
