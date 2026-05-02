import os

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from . import mocks

load_dotenv()

GLUE_DATABASE = os.getenv("GLUE_DATABASE", "default")
AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")

_glue = None


def client():
    global _glue
    if _glue is None:
        _glue = boto3.client("glue", region_name=AWS_REGION)
    return _glue


def _resolve(table_id: str) -> tuple[str, str]:
    if "." in table_id:
        db, name = table_id.split(".", 1)
    else:
        db, name = GLUE_DATABASE, table_id
    return db, name


def get_table_metadata(table_id: str) -> dict:
    if mocks.is_dry_run():
        return mocks.mock_glue_metadata(table_id)
    db, name = _resolve(table_id)
    try:
        resp = client().get_table(DatabaseName=db, Name=name)
    except (ClientError, BotoCoreError) as e:
        return {"table_id": table_id, "database": db, "name": name, "error": str(e)}

    t = resp["Table"]
    sd = t.get("StorageDescriptor", {})
    cols = [
        {"name": c["Name"], "type": c["Type"], "comment": c.get("Comment")}
        for c in sd.get("Columns", [])
    ]
    partitions = [
        {"name": p["Name"], "type": p["Type"]}
        for p in t.get("PartitionKeys", [])
    ]
    return {
        "table_id": table_id,
        "database": db,
        "name": name,
        "location": sd.get("Location"),
        "columns": cols,
        "partition_keys": partitions,
        "table_type": t.get("TableType"),
        "input_format": sd.get("InputFormat"),
    }
