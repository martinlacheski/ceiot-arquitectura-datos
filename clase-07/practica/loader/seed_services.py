#!/usr/bin/env python3
# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""Carga reproducible del manual PDF y del estado efímero de AIR-002."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from typing import Any

import boto3
import psycopg
import redis
from botocore import UNSIGNED
from botocore.config import Config
from pypdf import PdfReader
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from shared.settings import env_int

OBJECT_KEY = "manuales/env-x/v1/manual_ENV_X.pdf"
CONTENT_TYPE = "application/pdf"
REDIS_KEY = "iot:last-known:AIR-002"
REDIS_TTL_SECONDS = env_int("REDIS_TTL_SECONDS", 3600, minimum=1)


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Falta la variable requerida {name}")
    return value


def load_source(path: Path) -> dict[str, Any]:
    try:
        source = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"No se pudo leer la fuente versionada: {error}") from error
    expected_keys = {"schema_version", "document_id", "version", "title", "pages"}
    if set(source) != expected_keys:
        raise ValueError("La fuente del manual tiene campos inesperados o faltantes")
    if source["schema_version"] != 1 or source["version"] != 1:
        raise ValueError("Sólo se admite la versión 1 del esquema y del manual")
    if source["document_id"] != "env-x-manual":
        raise ValueError("El identificador del manual no coincide con el seed SQL")
    pages = source["pages"]
    if [page.get("page") for page in pages] != [1, 2]:
        raise ValueError("La fuente debe declarar exactamente las páginas 1 y 2")
    if any(not page.get("sections") for page in pages):
        raise ValueError("Cada página debe incluir al menos una sección")
    return source


def wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_pdf(source: dict[str, Any]) -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=A4,
        pageCompression=0,
        invariant=1,
    )
    pdf.setTitle(source["title"])
    pdf.setAuthor("Laboratorio CEIoT")
    pdf.setSubject(
        f"{source['document_id']} versión {source['version']}: fuente JSON versionada"
    )
    width, height = A4

    for page in source["pages"]:
        page_number = page["page"]
        pdf.setFont("Helvetica-Bold", 17)
        pdf.drawString(54, height - 62, source["title"])
        pdf.setFont("Helvetica", 9)
        pdf.drawString(
            54,
            height - 80,
            f"Documento {source['document_id']} · versión {source['version']}",
        )
        y = height - 120
        for section in page["sections"]:
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(54, y, section["section"])
            y -= 20
            pdf.setFont("Helvetica", 10.5)
            for line in wrap_text(section["text"], "Helvetica", 10.5, width - 108):
                if y < 78:
                    raise ValueError(f"El contenido desborda la página {page_number}")
                pdf.drawString(54, y, line)
                y -= 15
            y -= 16
        pdf.setFont("Helvetica-Oblique", 8.5)
        pdf.drawString(
            54,
            42,
            f"Proveniencia: manual-content.json · versión {source['version']} · página {page_number}/2",
        )
        pdf.showPage()

    pdf.save()
    rendered = output.getvalue()
    reader = PdfReader(io.BytesIO(rendered))
    if len(reader.pages) != 2:
        raise RuntimeError("El PDF generado no contiene exactamente dos páginas")
    for expected_page, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        marker = f"página {expected_page}/2"
        if marker not in text:
            raise RuntimeError(f"Falta la proveniencia esperada en la página {expected_page}")
    return rendered


def postgres_connection() -> psycopg.Connection[Any]:
    return psycopg.connect(
        host=required_env("POSTGRES_HOST"),
        port=int(required_env("POSTGRES_PORT")),
        user=required_env("POSTGRES_USER"),
        password=required_env("POSTGRES_PASSWORD"),
        dbname=required_env("POSTGRES_DB"),
    )


def mark_manual_pending(connection: psycopg.Connection[Any], source: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO manual_documents (
                document_id, version, title, object_key, content_type, storage_status
            ) VALUES (%s, %s, %s, %s, %s, 'pending_upload')
            ON CONFLICT (document_id, version) DO UPDATE
            SET title = EXCLUDED.title,
                object_key = EXCLUDED.object_key,
                content_type = EXCLUDED.content_type,
                storage_status = 'pending_upload'
            """,
            (
                source["document_id"],
                source["version"],
                source["title"],
                OBJECT_KEY,
                CONTENT_TYPE,
            ),
        )
    connection.commit()


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=required_env("SEAWEEDFS_S3_ENDPOINT"),
        region_name="us-east-1",
        config=Config(signature_version=UNSIGNED, retries={"max_attempts": 4}),
    )


def upload_and_verify(pdf_bytes: bytes, source: dict[str, Any]) -> None:
    client = s3_client()
    bucket = required_env("MANUAL_BUCKET")
    existing_buckets = {item["Name"] for item in client.list_buckets().get("Buckets", [])}
    if bucket not in existing_buckets:
        client.create_bucket(Bucket=bucket)

    digest = hashlib.sha256(pdf_bytes).hexdigest()
    client.put_object(
        Bucket=bucket,
        Key=OBJECT_KEY,
        Body=pdf_bytes,
        ContentType=CONTENT_TYPE,
        Metadata={
            "sha256": digest,
            "document-id": source["document_id"],
            "version": str(source["version"]),
            "pages": "2",
        },
    )
    head = client.head_object(Bucket=bucket, Key=OBJECT_KEY)
    if head.get("ContentType") != CONTENT_TYPE:
        raise RuntimeError("HEAD devolvió un tipo de contenido inesperado")
    if head.get("ContentLength") != len(pdf_bytes):
        raise RuntimeError("HEAD devolvió un tamaño distinto del PDF generado")
    if head.get("Metadata", {}).get("sha256") != digest:
        raise RuntimeError("HEAD no conservó la huella SHA-256 esperada")

    response = client.get_object(Bucket=bucket, Key=OBJECT_KEY)
    try:
        downloaded = response["Body"].read()
    finally:
        response["Body"].close()
    if downloaded != pdf_bytes:
        raise RuntimeError("GET no devolvió exactamente el PDF generado")


def mark_manual_available(connection: psycopg.Connection[Any], source: dict[str, Any]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE manual_documents
            SET object_key = %s,
                content_type = %s,
                storage_status = 'available'
            WHERE document_id = %s AND version = %s
            """,
            (OBJECT_KEY, CONTENT_TYPE, source["document_id"], source["version"]),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("No se pudo marcar exactamente un manual como disponible")
    connection.commit()


def latest_state(connection: psycopg.Connection[Any]) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT ON (variable)
                   variable, value::double precision, unit, quality, measured_at
            FROM measurements
            WHERE device_id = 'AIR-002'
            ORDER BY variable, measured_at DESC
            """
        )
        rows = cursor.fetchall()
    if not rows:
        raise RuntimeError("PostgreSQL no contiene historial para AIR-002")
    return {
        "device_id": "AIR-002",
        "source_of_truth": "postgres.measurements",
        "readings": {
            variable: {
                "value": value,
                "unit": unit,
                "quality": quality,
                "measured_at": measured_at.isoformat(),
            }
            for variable, value, unit, quality, measured_at in rows
        },
    }


def seed_redis(state: dict[str, Any]) -> int:
    client = redis.Redis(
        host=required_env("REDIS_HOST"),
        port=int(required_env("REDIS_PORT")),
        password=required_env("REDIS_PASSWORD"),
        decode_responses=True,
    )
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    client.set(REDIS_KEY, encoded, ex=REDIS_TTL_SECONDS)
    stored = client.get(REDIS_KEY)
    ttl = client.ttl(REDIS_KEY)
    if stored != encoded or not 0 < ttl <= REDIS_TTL_SECONDS:
        raise RuntimeError("Redis no conservó el estado con un TTL finito")
    return ttl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()

    source = load_source(args.source)
    with postgres_connection() as connection:
        mark_manual_pending(connection, source)
        pdf_bytes = render_pdf(source)
        upload_and_verify(pdf_bytes, source)
        mark_manual_available(connection, source)
        state = latest_state(connection)

    ttl = seed_redis(state)
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    print(
        "Carga verificada: "
        f"s3://{required_env('MANUAL_BUCKET')}/{OBJECT_KEY}, "
        f"PDF=2 páginas, sha256={digest}, Redis TTL={ttl}s."
    )
    print("PostgreSQL conserva el historial; Redis sólo acelera la última lectura.")


if __name__ == "__main__":
    main()
