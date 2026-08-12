#!/usr/bin/env python3
"""Convert a BIRD SQLite database to MySQL and load it.

Usage:
    python3 load_sqlite.py <sqlite_path> <mysql_database> [--host localhost] [--port 3306]
"""
import argparse
import sqlite3
import subprocess
import sys
import re


def sqlite_to_mysql_type(col_type):
    """Map SQLite column type to MySQL type."""
    col_type = col_type.upper().strip()
    if not col_type:
        return "TEXT"
    if "INT" in col_type:
        return "BIGINT"
    if "CHAR" in col_type or "TEXT" in col_type or "CLOB" in col_type:
        return "TEXT"
    if "REAL" in col_type or "FLOAT" in col_type or "DOUB" in col_type:
        return "DOUBLE"
    if "BLOB" in col_type:
        return "LONGBLOB"
    if "NUMERIC" in col_type or "DECIMAL" in col_type:
        return "DECIMAL(20,6)"
    return "TEXT"


def escape_value(val):
    """Escape a value for MySQL INSERT."""
    if val is None:
        return "NULL"
    if isinstance(val, (int, float)):
        return str(val)
    s = str(val)
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def convert_sqlite_to_mysql_sql(sqlite_path, database_name, drop_existing=True):
    """Read a SQLite database and produce MySQL-compatible SQL statements."""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    statements = []
    statements.append(f"CREATE DATABASE IF NOT EXISTS `{database_name}`;")
    statements.append(f"USE `{database_name}`;")
    statements.append("SET NAMES utf8mb4;")
    statements.append("SET FOREIGN_KEY_CHECKS = 0;")

    # Get all tables
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cursor.fetchall()

    for table in tables:
        table_name = table["name"]
        create_sql = table["sql"]

        # Get column info
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        columns = cursor.fetchall()

        # Build MySQL CREATE TABLE
        col_defs = []
        pk_cols = [c for c in columns if c["pk"]]
        for col in columns:
            col_name = col["name"]
            col_type = sqlite_to_mysql_type(col["type"])
            is_pk = col["pk"] == 1 and len(pk_cols) == 1
            # MySQL: TEXT/BLOB columns can't be PRIMARY KEY without length
            # Use VARCHAR(255) for PK columns that would otherwise be TEXT
            if is_pk and col_type in ("TEXT", "LONGBLOB"):
                col_type = "VARCHAR(255)"
            nullable = "NOT NULL" if col["notnull"] else ""
            pk = "PRIMARY KEY" if is_pk else ""
            # MySQL: TEXT/BLOB columns can't have default values
            default = ""
            if col["dflt_value"] is not None and col_type not in ("TEXT", "LONGBLOB"):
                default = f"DEFAULT {col['dflt_value']}"
            col_defs.append(f"  `{col_name}` {col_type} {nullable} {default} {pk}".strip())

        create_stmt = f"CREATE TABLE IF NOT EXISTS `{table_name}` (\n" + ",\n".join(col_defs) + "\n);"
        statements.append(f"DROP TABLE IF EXISTS `{table_name}`;")
        statements.append(create_stmt)

        # Get all rows
        try:
            cursor.execute(f'SELECT * FROM "{table_name}";')
            rows = cursor.fetchall()
        except Exception as e:
            statements.append(f"-- Error reading {table_name}: {e}")
            continue

        if rows:
            col_names = [col["name"] for col in columns]
            col_list = ", ".join(f"`{c}`" for c in col_names)

            # Batch inserts for efficiency
            batch_size = 100
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                values = []
                for row in batch:
                    vals = ", ".join(escape_value(row[c]) for c in col_names)
                    values.append(f"({vals})")
                insert = f"INSERT INTO `{table_name}` ({col_list}) VALUES\n" + ",\n".join(values) + ";"
                statements.append(insert)

    statements.append("SET FOREIGN_KEY_CHECKS = 1;")
    conn.close()
    return "\n\n".join(statements)


def main():
    parser = argparse.ArgumentParser(description="Convert SQLite to MySQL")
    parser.add_argument("sqlite_path", help="Path to SQLite database file")
    parser.add_argument("database_name", help="MySQL database name to create")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="agenttuning")
    parser.add_argument("--output", help="Write SQL to file instead of loading")
    args = parser.parse_args()

    sql = convert_sqlite_to_mysql_sql(args.sqlite_path, args.database_name)

    if args.output:
        with open(args.output, "w") as f:
            f.write(sql)
        print(f"SQL written to {args.output}")
    else:
        # Load directly into MySQL
        proc = subprocess.run(
            ["mysql", "-h", args.host, "-P", str(args.port),
             "-u", args.user, f"-p{args.password}"],
            input=sql,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(f"Error loading SQL: {proc.stderr}", file=sys.stderr)
            sys.exit(1)
        print(f"Database {args.database_name} loaded successfully")


if __name__ == "__main__":
    main()
