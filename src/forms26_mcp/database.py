"""Optional dictionary-only Oracle access. No caller-supplied SQL or DDL."""
import os

from .core import identifier

OBJECTS_SQL = """SELECT object_name, object_type, status FROM all_objects
WHERE owner = :owner AND object_name = :name
AND object_type IN ('TABLE', 'VIEW', 'PACKAGE', 'PACKAGE BODY', 'PROCEDURE', 'FUNCTION', 'SEQUENCE', 'SYNONYM')
ORDER BY object_type"""
COLUMNS_SQL = """SELECT column_name, data_type, data_length, data_precision,
data_scale, nullable FROM all_tab_columns
WHERE owner = :owner AND table_name = :name ORDER BY column_id"""
CONSTRAINTS_SQL = """SELECT c.constraint_name, c.constraint_type, c.status,
cc.column_name, cc.position, c.r_owner, c.r_constraint_name
FROM all_constraints c LEFT JOIN all_cons_columns cc
ON cc.owner = c.owner AND cc.constraint_name = c.constraint_name
AND cc.table_name = c.table_name
WHERE c.owner = :owner AND c.table_name = :name
ORDER BY c.constraint_name, cc.position"""


def inspect_objects(names: list[str]) -> dict:
    if not names or len(names) > 20:
        raise ValueError("Supply 1..20 simple unquoted object names")
    objects = list(dict.fromkeys(identifier(n) for n in names))
    required = ["ORACLE_DSN", "ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_SCHEMA"]
    if not all(os.environ.get(k) for k in required):
        return {"status": "not_configured", "required_environment": required,
                "note": "Set credentials on the server host; do not send passwords as tool arguments"}
    owner = identifier(os.environ["ORACLE_SCHEMA"])
    try:
        import oracledb
    except ImportError as exc:
        raise ValueError("Install the optional Oracle dependency: pip install '.[oracle]'") from exc
    kwargs = {"user": os.environ["ORACLE_USER"], "password": os.environ["ORACLE_PASSWORD"],
              "dsn": os.environ["ORACLE_DSN"], "tcp_connect_timeout": 10, "retry_count": 0}
    if os.environ.get("ORACLE_CONFIG_DIR"):
        kwargs["config_dir"] = os.environ["ORACLE_CONFIG_DIR"]
    if os.environ.get("ORACLE_WALLET_LOCATION"):
        kwargs["wallet_location"] = os.environ["ORACLE_WALLET_LOCATION"]
    if os.environ.get("ORACLE_WALLET_PASSWORD"):
        kwargs["wallet_password"] = os.environ["ORACLE_WALLET_PASSWORD"]
    try:
        with oracledb.connect(**kwargs) as connection:
            connection.call_timeout = 10_000
            result = {"status": "ok", "schema": owner, "database_version": connection.version,
                      "objects": [], "visibility": "Only objects visible to the configured account; absence does not establish nonexistence"}
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                for name in objects:
                    record = {"name": name}
                    for key, sql in [("objects", OBJECTS_SQL), ("columns", COLUMNS_SQL), ("constraints", CONSTRAINTS_SQL)]:
                        cursor.execute(sql, owner=owner, name=name)
                        columns = [x[0].lower() for x in cursor.description]
                        rows = cursor.fetchmany(1001)
                        record[key] = [dict(zip(columns, row)) for row in rows[:1000]]
                        record[key + "_truncated"] = len(rows) > 1000
                    result["objects"].append(record)
            connection.rollback()
            return result
    except oracledb.Error:
        # Driver messages may contain DSNs and usernames. Keep tool errors generic.
        raise ValueError("Oracle dictionary inspection failed; check connectivity, wallet, schema visibility and grants on the server host") from None
