import os
import json
import logging

import pymysql
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_db_connection():
    """Connect to MySQL using environment variables."""
    try:
        return pymysql.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "ai_faq_generator"),
            cursorclass=pymysql.cursors.DictCursor,
            charset="utf8mb4",
            autocommit=False,
        )
    except Exception:
        logger.exception("Database connection error")
        return None


def _get_columns(cursor, table_name):
    """Get actual column names from an existing table."""
    allowed_tables = {"faq_generations", "faqs", "users"}

    if table_name not in allowed_tables:
        raise ValueError("Invalid table name")

    cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
    return {row["Field"] for row in cursor.fetchall()}


def _insert_row(cursor, table_name, values, columns):
    """Insert only columns that exist in the current database."""
    selected = [
        (key, value)
        for key, value in values.items()
        if key in columns
    ]

    if not selected:
        raise RuntimeError(f"No compatible columns found for {table_name}")

    names = ", ".join(f"`{key}`" for key, _ in selected)
    placeholders = ", ".join(["%s"] * len(selected))
    parameters = tuple(value for _, value in selected)

    cursor.execute(
        f"INSERT INTO `{table_name}` ({names}) VALUES ({placeholders})",
        parameters,
    )


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

def init_db():
    """
    Initialize missing tables from schema.sql.
    Existing tables and their data are not dropped.
    """
    conn = get_db_connection()

    if conn is None:
        logger.warning("Cannot initialize database: connection failed.")
        return

    try:
        schema_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "schema.sql",
        )

        with open(schema_path, "r", encoding="utf-8") as file:
            sql = file.read()

        with conn.cursor() as cursor:
            for statement in sql.split(";"):
                statement = statement.strip()

                if not statement:
                    continue

                # Use the database selected by DB_NAME.
                # Do not switch to a hard-coded database.
                if statement.upper().startswith("CREATE DATABASE"):
                    continue

                if statement.upper().startswith("USE "):
                    continue

                cursor.execute(statement)

        conn.commit()
        logger.info("Database initialization completed.")

    except Exception:
        conn.rollback()
        logger.exception("Database initialization failed.")

    finally:
        conn.close()


# --------------------------------------------------
# NORMALIZE OLD AND NEW DATABASE STRUCTURES
# --------------------------------------------------

def _normalize_generation(generation):
    """Map legacy database columns to the current application names."""
    if not generation:
        return None

    generation = dict(generation)

    generation["source_type"] = (
        generation.get("source_type")
        or generation.get("input_source")
        or "text"
    )

    generation["source_filename"] = (
        generation.get("source_filename")
        or generation.get("file_name")
    )

    settings = generation.get("settings")

    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except (ValueError, TypeError):
            settings = {}

    if not isinstance(settings, dict):
        settings = {}

    for key, default in (
        ("difficulty", "intermediate"),
        ("answer_length", "medium"),
        ("language", "English"),
        ("category", "General Knowledge"),
    ):
        generation[key] = generation.get(key) or settings.get(key) or default

    return generation


# --------------------------------------------------
# SAVE GENERATED FAQS
# --------------------------------------------------

def save_generation(
    title,
    source_type,
    source_filename,
    source_text,
    difficulty,
    answer_length,
    language,
    category,
    faqs_list,
):
    """Save one FAQ generation and its questions."""
    conn = get_db_connection()

    if conn is None:
        logger.error("Cannot save generation: database unavailable.")
        return None

    try:
        faqs_list = faqs_list or []

        settings = {
            "difficulty": difficulty,
            "answer_length": answer_length,
            "language": language,
            "category": category,
        }

        generation_values = {
            "title": title,
            "source_type": source_type,
            "input_source": source_type,
            "source_filename": source_filename,
            "file_name": source_filename,
            "source_text": source_text,
            "difficulty": difficulty,
            "answer_length": answer_length,
            "language": language,
            "category": category,
            "settings": json.dumps(settings, ensure_ascii=False),
            "faqs_json": json.dumps(faqs_list, ensure_ascii=False),
            "faq_count": len(faqs_list),
        }

        with conn.cursor() as cursor:
            generation_columns = _get_columns(
                cursor, "faq_generations"
            )

            _insert_row(
                cursor,
                "faq_generations",
                generation_values,
                generation_columns,
            )

            generation_id = cursor.lastrowid
            faq_columns = _get_columns(cursor, "faqs")

            for faq in faqs_list:
                faq_values = {
                    "generation_id": generation_id,
                    "question": faq.get("question", ""),
                    "answer": faq.get("answer", ""),
                    "category": faq.get("category") or category or "General",
                    "source_text": source_text,
                    "language": language,
                }

                _insert_row(
                    cursor,
                    "faqs",
                    faq_values,
                    faq_columns,
                )

        conn.commit()
        logger.info("Saved FAQ generation ID %s", generation_id)
        return generation_id

    except Exception:
        conn.rollback()
        logger.exception("Error saving FAQ generation")
        return None

    finally:
        conn.close()


# --------------------------------------------------
# FETCH FAQ GENERATION HISTORY
# --------------------------------------------------

def get_all_generations(search_query=""):
    """Fetch generations compatible with either database schema."""
    conn = get_db_connection()

    if conn is None:
        return []

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM faq_generations ORDER BY created_at DESC"
            )
            rows = cursor.fetchall() or []

            if search_query:
                search = search_query.lower()
                rows = [
                    row for row in rows
                    if search in str(row.get("title", "")).lower()
                ]

            results = []

            for row in rows:
                generation = _normalize_generation(row)
                generation_id = generation["id"]

                cursor.execute(
                    "SELECT COUNT(*) AS total FROM faqs "
                    "WHERE generation_id = %s",
                    (generation_id,),
                )
                faq_count = cursor.fetchone()["total"]

                # Legacy records may keep their FAQs only in faqs_json.
                if not faq_count:
                    saved_faqs = generation.get("faqs_json")

                    if isinstance(saved_faqs, str):
                        try:
                            saved_faqs = json.loads(saved_faqs)
                        except (ValueError, TypeError):
                            saved_faqs = []

                    if isinstance(saved_faqs, list):
                        faq_count = len(saved_faqs)

                generation["faq_count"] = (
                    faq_count or generation.get("faq_count") or 0
                )

                results.append(generation)

            return results

    except Exception:
        logger.exception("Error fetching generation history")
        return []

    finally:
        conn.close()


def get_generation(generation_id):
    """Fetch one generation and its FAQs."""
    conn = get_db_connection()

    if conn is None:
        return None

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM faq_generations WHERE id = %s",
                (generation_id,),
            )

            generation = cursor.fetchone()

            if not generation:
                return None

            generation = _normalize_generation(generation)

            cursor.execute(
                "SELECT * FROM faqs WHERE generation_id = %s ORDER BY id",
                (generation_id,),
            )

            faq_rows = cursor.fetchall() or []

            faqs = []

            for row in faq_rows:
                faqs.append({
                    "id": row.get("id"),
                    "question": row.get("question", ""),
                    "answer": row.get("answer", ""),
                    "category": row.get("category") or "General",
                })

            # Fall back to legacy JSON if no normalized FAQ rows exist.
            if not faqs:
                saved_faqs = generation.get("faqs_json")

                if isinstance(saved_faqs, str):
                    try:
                        saved_faqs = json.loads(saved_faqs)
                    except (ValueError, TypeError):
                        saved_faqs = []

                if isinstance(saved_faqs, list):
                    faqs = saved_faqs

            generation["faqs"] = faqs
            return generation

    except Exception:
        logger.exception("Error fetching generation ID %s", generation_id)
        return None

    finally:
        conn.close()


def get_recent_generations(limit=5):
    """Return recent FAQ generations."""
    try:
        return get_all_generations()[:max(0, int(limit))]
    except (ValueError, TypeError):
        return []


# --------------------------------------------------
# UPDATE GENERATION TITLE
# --------------------------------------------------

def update_generation_title(generation_id, new_title):
    conn = get_db_connection()

    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE faq_generations SET title = %s WHERE id = %s",
                (new_title, generation_id),
            )
            changed = cursor.rowcount > 0

        conn.commit()
        return changed

    except Exception:
        conn.rollback()
        logger.exception("Error updating generation title")
        return False

    finally:
        conn.close()


# --------------------------------------------------
# UPDATE FAQ
# --------------------------------------------------

def update_faq(faq_id, question, answer, category="General"):
    conn = get_db_connection()

    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            columns = _get_columns(cursor, "faqs")

            updates = []
            params = []

            if "question" in columns:
                updates.append("question = %s")
                params.append(question)

            if "answer" in columns:
                updates.append("answer = %s")
                params.append(answer)

            if "category" in columns:
                updates.append("category = %s")
                params.append(category)

            if not updates:
                return False

            params.append(faq_id)

            cursor.execute(
                f"UPDATE faqs SET {', '.join(updates)} WHERE id = %s",
                tuple(params),
            )
            changed = cursor.rowcount > 0

        conn.commit()
        return changed

    except Exception:
        conn.rollback()
        logger.exception("Error updating FAQ ID %s", faq_id)
        return False

    finally:
        conn.close()


# --------------------------------------------------
# DELETE FAQ
# --------------------------------------------------

def delete_faq(faq_id):
    conn = get_db_connection()

    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM faqs WHERE id = %s",
                (faq_id,),
            )
            changed = cursor.rowcount > 0

        conn.commit()
        return changed

    except Exception:
        conn.rollback()
        logger.exception("Error deleting FAQ ID %s", faq_id)
        return False

    finally:
        conn.close()


# --------------------------------------------------
# DELETE GENERATION
# --------------------------------------------------

def delete_generation(generation_id):
    conn = get_db_connection()

    if conn is None:
        return False

    try:
        with conn.cursor() as cursor:
            # Delete children first for compatibility with legacy tables.
            cursor.execute(
                "DELETE FROM faqs WHERE generation_id = %s",
                (generation_id,),
            )

            cursor.execute(
                "DELETE FROM faq_generations WHERE id = %s",
                (generation_id,),
            )

            deleted = cursor.rowcount > 0

        conn.commit()
        return deleted

    except Exception:
        conn.rollback()
        logger.exception("Error deleting generation ID %s", generation_id)
        return False

    finally:
        conn.close()


# --------------------------------------------------
# DASHBOARD STATISTICS
# --------------------------------------------------

def get_stats():
    """Calculate FAQ, generation, and PDF counts."""
    stats = {
        "total_faqs": 0,
        "total_generations": 0,
        "total_documents": 0,
    }

    conn = get_db_connection()

    if conn is None:
        return stats

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM faq_generations"
            )
            stats["total_generations"] = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) AS total FROM faqs")
            actual_faq_count = cursor.fetchone()["total"]

            cursor.execute("SELECT * FROM faq_generations")
            generations = cursor.fetchall() or []

            for row in generations:
                generation = _normalize_generation(row)
                source = str(generation.get("source_type", "")).lower()

                if source == "pdf":
                    stats["total_documents"] += 1

            # Include legacy FAQs stored only in JSON, without double-counting
            # generations whose FAQ rows already exist in the faqs table.
            legacy_only_count = 0

            for row in generations:
                generation_id = row["id"]

                cursor.execute(
                    "SELECT COUNT(*) AS total FROM faqs "
                    "WHERE generation_id = %s",
                    (generation_id,),
                )
                count = cursor.fetchone()["total"]

                if count == 0:
                    saved_faqs = row.get("faqs_json")

                    if isinstance(saved_faqs, str):
                        try:
                            saved_faqs = json.loads(saved_faqs)
                        except (ValueError, TypeError):
                            saved_faqs = []

                    if isinstance(saved_faqs, list):
                        legacy_only_count += len(saved_faqs)

            stats["total_faqs"] = actual_faq_count + legacy_only_count

        return stats

    except Exception:
        logger.exception("Error retrieving dashboard statistics")
        return stats

    finally:
        conn.close()


# --------------------------------------------------
# USER REGISTRATION
# --------------------------------------------------

def create_user(full_name, email, password):
    """Create an account using a securely hashed password."""
    conn = get_db_connection()

    if conn is None:
        return False, "Database connection failed."

    try:
        with conn.cursor() as cursor:
            columns = _get_columns(cursor, "users")

            user_values = {
                "full_name": full_name.strip(),
                "email": email.strip().lower(),
                "password_hash": generate_password_hash(password),
            }

            _insert_row(cursor, "users", user_values, columns)

        conn.commit()
        return True, "Account created successfully."

    except pymysql.err.IntegrityError:
        conn.rollback()
        return False, "This email is already registered."

    except Exception:
        conn.rollback()
        logger.exception("User registration failed")
        return False, "Could not create account."

    finally:
        conn.close()


def get_user_by_email(email):
    """Find a user by email address."""
    conn = get_db_connection()

    if conn is None:
        return None

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, full_name, email, password_hash
                FROM users
                WHERE email = %s
                """,
                (email.strip().lower(),),
            )
            return cursor.fetchone()

    except Exception:
        logger.exception("User lookup failed")
        return None

    finally:
        conn.close()


def verify_user_password(user, password):
    """Verify a submitted password."""
    if not user:
        return False

    try:
        return check_password_hash(user["password_hash"], password)
    except (KeyError, TypeError, ValueError):
        logger.exception("Password verification failed")
        return False
