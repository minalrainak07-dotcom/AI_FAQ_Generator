
def delete_faq(faq_id):
    """
    Delete a single FAQ by ID.
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
    """
    Delete a generation and all its FAQs in a transaction.
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
    """
    Retrieve statistics: total FAQs, total generations, and total PDF documents.
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
        if conn:
            conn.close()


def get_recent_generations(limit=5):
    """
    Retrieve the most recent generations with FAQ counts.
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
        if conn:
            conn.close()
