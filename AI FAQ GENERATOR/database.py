import os
import logging
import pymysql

logger = logging.getLogger(__name__)


def get_db_connection():
    """Create and return a new MySQL connection using environment variables."""
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
    """Save a generated FAQ collection and return its ID, or None on failure."""
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
                    INSERT INTO faqs (generation_id, question, answer, category)
                    VALUES (%s, %s, %s, %s)
                    """,
