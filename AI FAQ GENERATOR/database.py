import os
import logging
import pymysql
from werkzeug.security import generate_password_hash, check_password_hash
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
    """Return all generations, optionally filtered by title."""
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
    """Return one generation and its FAQs, or None if missing/unavailable."""
    conn = get_db_connection()
    if not conn:
        return None

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM faq_generations WHERE id = %s", (generation_id,)
            )
            gen = cur.fetchone()
            if not gen:
                return None

            cur.execute(
                """
                SELECT id, question, answer, category
                FROM faqs WHERE generation_id = %s
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
    """Update a generation title. Return True if a row was changed."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE faq_generations SET title = %s WHERE id = %s",
                (new_title, generation_id),
            )
            changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error("Error updating generation title: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


def update_faq(faq_id, question, answer, category="General"):
    """Update an existing FAQ. Return True if a row was changed."""
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
            changed = cursor.rowcount > 0
        conn.commit()
        return changed
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
            cursor.execute("DELETE FROM faqs WHERE id = %s", (faq_id,))
            changed = cursor.rowcount > 0
        conn.commit()
        return changed
    except Exception as e:
        logger.error("Error deleting FAQ ID %s: %s", faq_id, e)
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_generation(generation_id):
    """Delete a generation and its FAQs in one transaction."""
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM faqs WHERE generation_id = %s", (generation_id,)
            )
            cursor.execute(
                "DELETE FROM faq_generations WHERE id = %s", (generation_id,)
            )
            deleted_generation = cursor.rowcount > 0
        conn.commit()
        return deleted_generation
    except Exception as e:
        logger.error("Error deleting generation ID %s: %s", generation_id, e)
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
            cursor.execute("SELECT COUNT(*) AS total_faqs FROM faqs")
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
            "total_documents": (
                int(doc_row["total_documents"]) if doc_row else 0
            ),
        }
    except Exception as e:
        logger.error("Error retrieving stats: %s", e)
        return default_stats
    finally:
        conn.close()


def get_recent_generations(limit=5):
    """Return the most recent generations with FAQ counts."""
    conn = get_db_connection()
    if not conn:
        return []

    try:
        query = """
            SELECT g.id, g.title, g.source_type, g.source_filename,
                   g.difficulty, g.answer_length, g.language, g.category,
                   COUNT(f.id) AS faq_count, g.created_at, g.updated_at
            FROM faq_generations g
            LEFT JOIN faqs f ON g.id = f.generation_id
            GROUP BY g.id, g.title, g.source_type, g.source_filename,
                     g.difficulty, g.answer_length, g.language, g.category,
                     g.created_at, g.updated_at
            ORDER BY g.created_at DESC
            LIMIT %s
        """
        with conn.cursor() as cursor:
            cursor.execute(query, (int(limit),))
            return cursor.fetchall() or []
    except Exception as e:
        logger.error("Error fetching recent generations: %s", e)
        return []
    finally:
        conn.close()

from werkzeug.security import generate_password_hash, check_password_hash


def create_user(full_name, email, password):
    """Create a user account with a securely hashed password."""
    conn = get_db_connection()
    if conn is None:
        return False, "Database connection failed."

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (full_name, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (
                    full_name.strip(),
                    email.strip().lower(),
                    generate_password_hash(password),
                ),
            )
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
    """Find a registered user by email."""
    conn = get_db_connection()
    if conn is None:
        return None

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM users WHERE email = %s",
                (email.strip().lower(),),
            )
            return cursor.fetchone()
    except Exception:
        logger.exception("User lookup failed")
        return None
    finally:
        conn.close()


def verify_user_password(user, password):
    """Verify a password against its stored hash."""
    if not user:
        return False
    return check_password_hash(user["password_hash"], password)

def create_user(full_name, email, password):
    """Create a user account with a securely hashed password."""
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed")

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    full_name VARCHAR(150) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            cur.execute(
                "SELECT id FROM users WHERE email = %s",
                (email,)
            )
            if cur.fetchone():
                return False

            password_hash = generate_password_hash(password)

            cur.execute("""
                INSERT INTO users (full_name, email, password_hash)
                VALUES (%s, %s, %s)
            """, (full_name, email, password_hash))

        conn.commit()
        return True

    except Exception:
        conn.rollback()
        logger.exception("Error creating user")
        raise
    finally:
        conn.close()


def get_user_by_email(email):
    """Find a registered user by email."""
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Database connection failed")

    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    full_name VARCHAR(150) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute(
                "SELECT id, full_name, email, password_hash "
                "FROM users WHERE email = %s",
                (email,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def verify_user_password(user, password):
    """Verify a submitted password against its stored hash."""
    if not user:
        return False

    stored_hash = user.get("password_hash")
    if not stored_hash:
        return False

    return check_password_hash(stored_hash, password)
