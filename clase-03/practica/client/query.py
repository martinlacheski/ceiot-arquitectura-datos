"""Consulta mínima con parámetros del driver; no concatena datos en el SQL."""

import os
from datetime import datetime

import psycopg  # type: ignore[import-not-found]


def required_datetime(name: str) -> datetime:
    value = os.environ[name]
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def main() -> None:
    parameters = (
        os.environ["DEVICE_SERIAL"],
        os.environ["VARIABLE"],
        required_datetime("START_AT"),
        required_datetime("END_AT"),
    )

    with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            with connection.cursor() as cursor:
                # pi-lens-ignore: python-sql-injection
                cursor.execute(
                    """
                    SELECT
                        d.serial_number,
                        m.variable,
                        m.value,
                        m.unit,
                        m.recorded_at
                    FROM measurements AS m
                    INNER JOIN devices AS d ON d.id = m.device_id
                    WHERE d.serial_number = %s
                      AND m.variable = %s
                      AND m.recorded_at >= %s
                      AND m.recorded_at < %s
                    ORDER BY m.recorded_at ASC, m.id ASC;
                    """,
                    parameters,
                )
                rows = cursor.fetchall()

    print("serial_number | variable | value | unit | recorded_at")
    for row in rows:
        print(" | ".join(str(value) for value in row))
    print(f"rows={len(rows)}")


if __name__ == "__main__":
    main()
