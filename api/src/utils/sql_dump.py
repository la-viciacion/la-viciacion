"""A `.sql` backup of the whole database, made by the API itself (admin panel -> Sistema -> Copia de seguridad).

It is what `mariadb-dump` would give for this schema, written with the SQL the server already speaks, so the API
image needs no extra client: for every table `DROP TABLE IF EXISTS`, the server's own `SHOW CREATE TABLE` (keys,
generated columns and all) and the rows as multi-row `INSERT`s. Generated columns (the `season` ones) are left out
of the inserts, as the database computes them. It restores with a plain `mariadb < backup.sql` into the empty
database of a new environment (or `db/init/`, see docs/deployment.md), `alembic_version` included.

Everything is read in one transaction with a repeatable-read snapshot, so the tables agree with each other even
while the app keeps working, and rows are streamed in batches: nothing is built in memory but one batch.
The file holds password hashes, avatars and encrypted tokens: it is for admins only and is as sensitive as the
database itself. The endpoint serves it gzipped (`gzip_stream`).
"""
import datetime
import decimal
import zlib
from typing import Iterator

from sqlalchemy.engine import Engine

BATCH = 200  # rows per INSERT
HEADER = """-- La Viciación: database backup
-- Taken {when}. Restore it into an empty database: mariadb -u root -p <database> < backup.sql
/*!40101 SET NAMES utf8mb4 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;

"""
FOOTER = """
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
-- Dump completed
"""

# what a string literal must escape (the sql_mode set in the header keeps backslash escapes on)
_ESCAPES = {"\\": "\\\\", "'": "\\'", "\0": "\\0", "\n": "\\n", "\r": "\\r", "\x1a": "\\Z"}


def quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def quote_text(text: str) -> str:
    return "'" + "".join(_ESCAPES.get(c, c) for c in text) + "'"


def sql_value(value) -> str:
    """A Python value as an SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, decimal.Decimal)):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        return "0x" + data.hex() if data else "''"
    if isinstance(value, datetime.datetime):
        return quote_text(value.isoformat(sep=" "))
    return quote_text(str(value))


def insert_statement(table: str, columns: list[str], rows: list[tuple]) -> str:
    names = ", ".join(quote_identifier(c) for c in columns)
    values = ",\n".join("(" + ", ".join(sql_value(v) for v in row) + ")" for row in rows)
    return f"INSERT INTO {quote_identifier(table)} ({names}) VALUES\n{values};\n"


def _tables(conn) -> list[str]:
    rows = conn.exec_driver_sql(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE' ORDER BY table_name"
    )
    return [r[0] for r in rows]


def _stored_columns(conn, table: str) -> list[str]:
    """The columns the INSERTs carry: every one that is not generated."""
    rows = conn.exec_driver_sql(
        "SELECT column_name, extra, generation_expression FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    return [name for name, extra, generated in rows if "GENERATED" not in (extra or "").upper() and not generated]


def dump(engine: Engine, now: datetime.datetime | None = None) -> Iterator[str]:
    """The backup as a stream of text chunks."""
    now = now or datetime.datetime.now()
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        yield HEADER.format(when=now.replace(microsecond=0).isoformat(sep=" "))
        for table in _tables(conn):
            quoted = quote_identifier(table)
            create = conn.exec_driver_sql(f"SHOW CREATE TABLE {quoted}").one()[1]
            yield f"--\n-- Table {quoted}\n--\n\nDROP TABLE IF EXISTS {quoted};\n{create};\n\n"
            columns = _stored_columns(conn, table)
            if not columns:
                continue
            select = f"SELECT {', '.join(quote_identifier(c) for c in columns)} FROM {quoted}"
            result = conn.execution_options(stream_results=True).exec_driver_sql(select)
            for batch in result.partitions(BATCH):
                yield insert_statement(table, columns, [tuple(row) for row in batch])
            yield "\n"
        yield FOOTER


def gzip_stream(chunks: Iterator[str]) -> Iterator[bytes]:
    """The text chunks as a gzip stream (the images are hex in the dump, which compresses to about half)."""
    packer = zlib.compressobj(wbits=31)  # 16 + 15: a gzip container, so `gunzip` and `.sql.gz` in db/init/ read it
    for chunk in chunks:
        if data := packer.compress(chunk.encode("utf-8")):
            yield data
    yield packer.flush()
