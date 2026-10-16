
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

