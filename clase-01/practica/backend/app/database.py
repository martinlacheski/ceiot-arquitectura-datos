import os

import psycopg
from psycopg.rows import dict_row


def get_connection() -> psycopg.Connection:
    return psycopg.connect(
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        row_factory=dict_row,
    )
