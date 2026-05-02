import os
from datetime import datetime, timezone
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

DB_NAME = os.getenv("MONGO_DB_NAME", "qa_agent")

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        conn = os.getenv("conn_string") or os.getenv("MONGODB_URI")
        if not conn:
            user = os.getenv("username")
            pw = os.getenv("mongo_db_pass")
            if not (user and pw):
                raise RuntimeError("Mongo connection not configured. Set conn_string or username+mongo_db_pass in .env")
            host = os.getenv("MONGO_HOST")
            if not host:
                raise RuntimeError("conn_string preferred; or set MONGO_HOST")
            conn = f"mongodb+srv://{quote_plus(user)}:{quote_plus(pw)}@{host}/?retryWrites=true&w=majority"
        _client = MongoClient(conn)
    return _client


def get_db():
    return get_client()[DB_NAME]


def collections():
    db = get_db()
    return {
        "pipeline_runs": db.pipeline_runs,
        "table_understandings": db.table_understandings,
        "pending_questions": db.pending_questions,
        "user_answers": db.user_answers,
        "executed_queries": db.executed_queries,
        "findings": db.findings,
        "final_reports": db.final_reports,
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_indexes() -> None:
    cols = collections()
    cols["pipeline_runs"].create_index("status")
    cols["pipeline_runs"].create_index("run_id", unique=True)
    cols["pending_questions"].create_index([("run_id", 1), ("question_id", 1)], unique=True)
    cols["user_answers"].create_index("question_id")
    cols["user_answers"].create_index([("run_id", 1), ("answered_at", 1)])
    cols["table_understandings"].create_index("table_id")
    cols["executed_queries"].create_index("run_id")
    cols["findings"].create_index("run_id")
    cols["final_reports"].create_index("run_id", unique=True)


def update_run_status(run_id: str, status: str, **extra) -> None:
    cols = collections()
    cols["pipeline_runs"].update_one(
        {"run_id": run_id},
        {"$set": {"status": status, "updated_at": now_utc(), **extra}},
        upsert=True,
    )
