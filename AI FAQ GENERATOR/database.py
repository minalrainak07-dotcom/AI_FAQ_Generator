import os
import logging
import pymysql

logger = logging.getLogger(__name__)


def get_db_connection():
    """Create and return a new MySQL connection."""
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
    except Exception as e:
        logger.error("Database connection error: %s", e)
        return None


def init_db():
    """Initialize database tables using schema.sql."""
    conn = get_db_connection()
    if not conn:
        logger.warning("Cannot initialize database: connection failed.")
        return

    try:
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

        with open(schema_path, "r", encoding="utf-8") as f:
            sql = f.read()

        with conn.cursor() as cur:
            for statement in sql.split(";"):
                stmt = statement.strip()
                if stmt:
                    cur.execute(stmt)

        conn.commit()
        logger.info("Database initialized successfully.")

    except Exception as e:
        logger.error("Error initializing database: %s", e)
        conn.rollback()

    finally:
        conn.close()


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
    """Save a generated FAQ collection and return its ID."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO faq_generations
                (title, source_type, source_filename, source_text,
                 difficulty, answer_length, language, category)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    title,
                    source_type,
                    source_filename,
                    source_text,
                    difficulty,
                    answer_length,
                    language,
                    category,
                ),
            )

            generation_id = cur.lastrowid

            for faq in faqs_list:
                cur.execute(
                    """
                    INSERT INTO faqs
                    (generation_id, question, answer, category)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        generation_id,
                        faq.get("question", ""),
                        faq.get("answer", ""),
                        faq.get("category", "General"),
                    ),
                )

        conn.commit()
        return generation_id

    except Exception as e:
        logger.error("Error saving generation: %s", e)
        conn.rollback()
        return None

    finally:
        conn.close()


def get_all_generations(search_query=""):
    """Return generations, optionally filtered by title."""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        query = """
            SELECT g.id, g.title, g.source_type, g.source_filename,
                   g.difficulty, g.answer_length, g.language, g.category,
                   g.created_at, g.updated_at, COUNT(f.id) AS faq_count
            FROM faq_generations g
            LEFT JOIN faqs f ON g.id = f.generation_id
        """
        params = []

        if search_query:
            query += " WHERE g.title LIKE %s"
            params.append(f"%{search_query}%")

        query += " GROUP BY g.id ORDER BY g.created_at DESC"

        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()

    except Exception as e:
        logger.error("Error fetching generations: %s", e)
        return []

    finally:
        conn.close()


def get_generation(generation_id):
    """Return one generation and its FAQs."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM faq_generations WHERE id = %s",
                (generation_id,),
            )
            gen = cur.fetchone()

            if not gen:
                return None

            cur.execute(
                """
                SELECT id, question, answer, category
                FROM faqs
                WHERE generation_id = %s
                """,
                (generation_id,),
            )

            gen["faqs"] = cur.fetchall()
            return gen

    except Exception as e:
        logger.error("Error fetching generation %s: %s", generation_id, e)
        return None

    finally:
        conn.close()


def update_generation_title(generation_id, new_title):
    """Update the title of a generation."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE faq_generations SET title = %s WHERE id = %s",
                (new_title, generation_id),
            )

        conn.commit()
        return True

    except Exception as e:
        logger.error("Error updating generation title: %s", e)
        conn.rollback()
        return False

    finally:
        conn.close()


def update_faq(faq_id, question, answer, category="General"):
    """Update an existing FAQ."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE faqs
                SET question = %s, answer = %s, category = %s
                WHERE id = %s
                """,
                (question, answer, category, faq_id),
            )

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        logger.error("Error updating FAQ ID %s: %s", faq_id, e)
        conn.rollback()
        return False

    finally:
        conn.close()


def delete_faq(faq_id):
    """Delete one FAQ by its ID."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM faqs WHERE id = %s",
                (faq_id,),
            )

        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        logger.error("Error deleting FAQ ID %s: %s", faq_id, e)
        conn.rollback()
        return False

    finally:
        conn.close()


def delete_generation(generation_id):
    """Delete a generation and all its FAQs."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM faqs WHERE generation_id = %s",
                (generation_id,),
            )
            cursor.execute(
                "DELETE FROM faq_generations WHERE id = %s",
                (generation_id,),
            )

        conn.commit()
        return True

    except Exception as e:
        logger.error("Error deleting generation: %s", e)
        conn.rollback()
        return False

    finally:
        conn.close()


def get_stats():
    """Return counts for FAQs, generations, and PDF documents."""
    default_stats = {
        "total_faqs": 0,
        "total_generations": 0,
        "total_documents": 0,
    }

    conn = get_db_connection()
    if not conn:
        return default_stats

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total_generations FROM faq_generations"
            )
            gen_row = cursor.fetchone()

            cursor.execute(
                "SELECT COUNT(*) AS total_faqs FROM faqs"
            )
            faq_row = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*) AS total_documents
                FROM faq_generations
                WHERE source_type = 'pdf'
                """
            )
            doc_row = cursor.fetchone()

        return {
            "total_faqs": int(faq_row["total_faqs"]) if faq_row else 0,
            "total_generations": (
                int(gen_row["total_generations"]) if gen_row else 0
            ),
