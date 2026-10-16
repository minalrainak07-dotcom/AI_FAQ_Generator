import os
import logging
import pymysql

logger = logging.getLogger(__name__)

def get_db_connection():
    """Create and return a new MySQL connection using environment variables.
    Returns None on failure and logs the error.
    """
    try:
        conn = pymysql.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', '3306')),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'ai_faq_generator'),
            cursorclass=pymysql.cursors.DictCursor,
            charset='utf8mb4',
            autocommit=False
        )
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None

def init_db():
    """Initialize the database schema from schema.sql.
    This will create the tables if they do not exist.
    """
    conn = get_db_connection()
    if not conn:
        logger.warning("Cannot initialize database because connection failed.")
        return
    try:
        with conn.cursor() as cur:
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
            with open(schema_path, 'r', encoding='utf-8') as f:
                sql = f.read()
            # Execute each statement individually to avoid multi‑statement issues.
            for statement in sql.split(';'):
                stmt = statement.strip()
                if stmt:
                    cur.execute(stmt)
        conn.commit()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        conn.close()

def save_generation(title, source_type, source_filename, source_text, difficulty, answer_length, language, category, faqs_list):
    """Insert a new generation and its FAQs into the database.
    Returns the generated generation_id or None on failure.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            gen_sql = """
                INSERT INTO faq_generations
                (title, source_type, source_filename, source_text, difficulty, answer_length, language, category)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(gen_sql, (
                title,
                source_type,
                source_filename,
                source_text,
                difficulty,
                answer_length,
                language,
                category
            ))
            generation_id = cur.lastrowid
            # Insert FAQs
            faq_sql = """
                INSERT INTO faqs (generation_id, question, answer, category)
                VALUES (%s, %s, %s, %s)
            """
            for faq in faqs_list:
                cur.execute(faq_sql, (
                    generation_id,
                    faq.get('question', ''),
                    faq.get('answer', ''),
                    faq.get('category', 'General')
                ))
        conn.commit()
        return generation_id
    except Exception as e:
        logger.error(f"Error saving generation: {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def get_all_generations(search_query=''):
    """Return a list of generation dicts, optionally filtered by title search.
    """
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            base_sql = """
                SELECT g.id, g.title, g.source_type, g.source_filename, g.difficulty,
                       g.answer_length, g.language, g.category, g.created_at, g.updated_at,
                       COUNT(f.id) AS faq_count
                FROM faq_generations g
                LEFT JOIN faqs f ON g.id = f.generation_id
            """
            params = []
            if search_query:
                base_sql += " WHERE g.title LIKE %s"
                params.append(f"%{search_query}%")
            base_sql += " GROUP BY g.id ORDER BY g.created_at DESC"
            cur.execute(base_sql, params)
            rows = cur.fetchall()
            return rows
    except Exception as e:
        logger.error(f"Error fetching generations: {e}")
        return []
    finally:
        conn.close()

def get_generation(generation_id):
    """Retrieve a single generation with its FAQs.
    Returns a dict with generation fields and a list under 'faqs'.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM faq_generations WHERE id = %s", (generation_id,))
            gen = cur.fetchone()
            if not gen:
                return None
            cur.execute("SELECT id, question, answer, category FROM faqs WHERE generation_id = %s", (generation_id,))
            faqs = cur.fetchall()
            gen['faqs'] = faqs
            return gen
    except Exception as e:
        logger.error(f"Error fetching generation {generation_id}: {e}")
        return None
    finally:
        conn.close()

def update_generation_title(generation_id, new_title):
    """Update the title of a generation. Returns True on success."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE faq_generations SET title = %s WHERE id = %s", (new_title, generation_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error updating title for generation {generation_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def delete_faq(faq_id):
    """Delete a single FAQ by ID.
    Returns True on success, False on failure.
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM faqs WHERE id = %s", (faq_id,))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting FAQ ID {faq_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_generation(generation_id):
    """Delete a generation and all its FAQs in a transaction.
    Returns True on success, False on failure.
    """
    conn = get_db_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM faqs WHERE generation_id = %s", (generation_id,))
            cursor.execute("DELETE FROM faq_generations WHERE id = %s", (generation_id,))
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error deleting generation ID {generation_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_stats():
    """Retrieve statistics: total FAQs, total generations, and total PDF documents.
    Returns a dict with integer counts.
    """
    default_stats = {
        'total_faqs': 0,
        'total_generations': 0,
        'total_documents': 0
    }
    conn = get_db_connection()
    if not conn:
        return default_stats
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total_generations FROM faq_generations")
            gen_row = cursor.fetchone()
            total_generations = gen_row['total_generations'] if gen_row else 0
            cursor.execute("SELECT COUNT(*) AS total_faqs FROM faqs")
            faq_row = cursor.fetchone()
            total_faqs = faq_row['total_faqs'] if faq_row else 0
            cursor.execute("SELECT COUNT(*) AS total_documents FROM faq_generations WHERE source_type = 'pdf'")
            doc_row = cursor.fetchone()
            total_documents = doc_row['total_documents'] if doc_row else 0
            return {
                'total_faqs': int(total_faqs),
                'total_generations': int(total_generations),
                'total_documents': int(total_documents)
            }
    except Exception as e:
        logger.error(f"Error retrieving stats: {e}")
        return default_stats
    finally:
        conn.close()

def get_recent_generations(limit=5):
    """Retrieve the most recent generations with FAQ counts.
    """
    conn = get_db_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT g.id, g.title, g.source_type, g.source_filename,
                       g.difficulty, g.answer_length, g.language, g.category,
                       COUNT(f.id) AS faq_count,
                       g.created_at, g.updated_at
                FROM faq_generations g
                LEFT JOIN faqs f ON g.id = f.generation_id
                GROUP BY g.id, g.title, g.source_type, g.source_filename,
                         g.difficulty, g.answer_length, g.language, g.category,
                         g.created_at, g.updated_at
                ORDER BY g.created_at DESC
                LIMIT %s
            """
            cursor.execute(query, (int(limit),))
            results = cursor.fetchall()
            return results if results is not None else []
    except Exception as e:
        logger.error(f"Error fetching recent generations: {e}")
        return []
    finally:
        conn.close()
