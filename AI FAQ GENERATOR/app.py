import os
import io
import json
import logging
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from flask import (
    request, session, flash,
    redirect, url_for, render_template
)
from database import (
    create_user,
    get_user_by_email,
    verify_user_password
)
from database import (
    get_db_connection,
    init_db,
    save_generation,
    get_all_generations,
    get_generation,
    update_generation_title,
    update_faq,
    delete_faq,
    delete_generation,
    get_stats,
    get_recent_generations
)
from faq_generator import generate_faqs
from pdf_processor import validate_pdf, extract_text_from_pdf
from export_service import export_txt, export_csv, export_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Flask application
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'default-dev-secret-key-change-in-production')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB limit
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("signup.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("signup.html")

        try:
            existing_user = get_user_by_email(email)

            if existing_user:
                flash("This email is already registered.", "error")
                return render_template("signup.html")

            create_user(full_name, email, password)

            flash("Signup successful! Please log in.", "success")
            return redirect(url_for("login"))

        except Exception:
            app.logger.exception("Signup failed")
            flash("Account creation failed. Please check the database.", "error")
            return render_template("signup.html")

    return render_template("signup.html")
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter email and password.", "error")
            return render_template("login.html")

        try:
            user = get_user_by_email(email)

            if user and verify_user_password(user, password):
                session["user_id"] = user["id"]
                session["user_name"] = user["full_name"]
                flash("Login successful!", "success")
                return redirect(url_for("index"))

            flash("Invalid email or password.", "error")

        except Exception:
            app.logger.exception("Login failed")
            flash("Login failed. Please check the database connection.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# Ensure uploads directory exists
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Attempt database initialization on startup
try:
    init_db()
except Exception as e:
    logger.warning(f"Database initialization deferred or unavailable: {e}")


# ==========================================
# PAGE ROUTES
# ==========================================

@app.route('/')
def index():
    """
    Dashboard page displaying platform metrics and recent FAQ generations.
    """
    try:
        stats = get_stats()
        recent_generations = get_recent_generations(limit=5)
    except Exception as e:
        logger.error(f"Error fetching dashboard data: {e}")
        stats = {'total_faqs': 0, 'total_generations': 0, 'total_documents': 0}
        recent_generations = []

    return render_template('index.html', stats=stats, recent_generations=recent_generations)


@app.route('/generate')
def generate_page():
    """
    FAQ Generation interface where users can upload PDFs, input text, or specify topics.
    """
    return render_template('generate.html')


@app.route('/history')
def history_page():
    """
    Historical list of FAQ generations with search capability.
    """
    search_query = request.args.get('search', '').strip()
    try:
        generations = get_all_generations(search_query=search_query)
    except Exception as e:
        logger.error(f"Error retrieving generation history: {e}")
        generations = []
        flash("Could not connect to database to load history.", "warning")

    return render_template('history.html', generations=generations, search_query=search_query)


@app.route('/about')
def about_page():
    """
    Application overview and architecture information.
    """
    return render_template('about.html')


@app.route('/results/new')
def results_new_page():
    """
    Results page for newly generated (unsaved) FAQs.
    The frontend will load data from sessionStorage.
    """
    return render_template('results.html', generation=None)


@app.route('/results/<int:generation_id>')
def results_page(generation_id):
    """
    Results and management page for a specific FAQ generation.
    """
    try:
        generation = get_generation(generation_id)
        if not generation:
            flash(f"Generation #{generation_id} was not found.", "danger")
            return redirect(url_for('history_page'))
        return render_template('results.html', generation=generation)
    except Exception as e:
        logger.error(f"Error fetching results for generation #{generation_id}: {e}")
        flash("An error occurred while loading the FAQ details.", "danger")
        return redirect(url_for('history_page'))


# ==========================================
# API ROUTES
# ==========================================

@app.route('/api/upload-pdf', methods=['POST'])
def api_upload_pdf():
    """
    Upload and extract text from a PDF file.
    """
    file = None
    if 'file' in request.files:
        file = request.files['file']
    elif 'pdf' in request.files:
        file = request.files['pdf']

    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file provided in request."}), 400

    result = extract_text_from_pdf(file)
    if not result.get("success"):
        return jsonify(result), 400

    return jsonify(result), 200


@app.route('/api/generate', methods=['POST'])
def api_generate():
    """
    Generate FAQs via Groq AI based on user parameters.
    Does not automatically save to database.
    """
    data = request.get_json(silent=True) or {}

    source_type = str(data.get('source_type', 'text')).strip().lower()
    source_text = str(data.get('source_text', '')).strip()
    source_filename = data.get('source_filename', None)
    num_faqs_raw = data.get('num_faqs', 5)
    difficulty = str(data.get('difficulty', 'intermediate')).strip().lower()
    answer_length = str(data.get('answer_length', 'medium')).strip().lower()
    language = str(data.get('language', 'English')).strip()
    category = str(data.get('category', 'General Knowledge')).strip()

    # Input validations
    if source_type not in ['pdf', 'text', 'topic']:
        return jsonify({"success": False, "error": "Invalid source_type. Must be 'pdf', 'text', or 'topic'."}), 400

    if not source_text:
        return jsonify({"success": False, "error": "Source text or topic prompt cannot be empty."}), 400

    try:
        num_faqs = int(num_faqs_raw)
        if num_faqs < 1 or num_faqs > 30:
            return jsonify({"success": False, "error": "Number of FAQs must be between 1 and 30."}), 400
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Invalid number of FAQs specified."}), 400

    if difficulty not in ['beginner', 'intermediate', 'advanced']:
        difficulty = 'intermediate'

    if answer_length not in ['short', 'medium', 'detailed']:
        answer_length = 'medium'

    # Call AI generation service
    ai_result = generate_faqs(
        source_text=source_text,
        source_type=source_type,
        num_faqs=num_faqs,
        difficulty=difficulty,
        answer_length=answer_length,
        language=language,
        category=category
    )

    if not ai_result.get("success"):
        return jsonify(ai_result), 500

    # Include parameters in returned payload for convenient client-side reference
    return jsonify({
        "success": True,
        "data": ai_result.get("data"),
        "meta": {
            "source_type": source_type,
            "source_filename": source_filename,
            "difficulty": difficulty,
            "answer_length": answer_length,
            "language": language,
            "category": category
        }
    }), 200


@app.route('/api/save', methods=['POST'])
def api_save():
    """
    Save generated FAQs to the database.
    """
    data = request.get_json(silent=True) or {}

    title = str(data.get('title', 'Generated FAQs')).strip()
    source_type = str(data.get('source_type', 'text')).strip().lower()
    source_filename = data.get('source_filename', None)
    source_text = data.get('source_text', '')
    difficulty = str(data.get('difficulty', 'intermediate')).strip().lower()
    answer_length = str(data.get('answer_length', 'medium')).strip().lower()
    language = str(data.get('language', 'English')).strip()
    category = str(data.get('category', 'General Knowledge')).strip()
    faqs = data.get('faqs', [])

    if not title:
        title = "Generated FAQs"

    if source_type not in ['pdf', 'text', 'topic']:
        source_type = 'text'

    if not isinstance(faqs, list) or len(faqs) == 0:
        return jsonify({"success": False, "error": "Cannot save empty FAQs list."}), 400

    try:
        generation_id = save_generation(
            title=title,
            source_type=source_type,
            source_filename=source_filename,
            source_text=source_text,
            difficulty=difficulty,
            answer_length=answer_length,
            language=language,
            category=category,
            faqs_list=faqs
        )

        if not generation_id:
            return jsonify({
                "success": False,
                "error": "Failed to save generation to database. Please check database connectivity."
            }), 500

        return jsonify({
            "success": True,
            "generation_id": generation_id,
            "message": "FAQs saved successfully."
        }), 201

    except Exception as e:
        logger.error(f"Error in api_save: {e}")
        return jsonify({"success": False, "error": f"Failed to save: {str(e)}"}), 500


@app.route('/api/generations', methods=['GET'])
def api_get_generations():
    """
    List all generations as JSON with optional search filter.
    """
    search_query = request.args.get('search', '').strip()
    try:
        generations = get_all_generations(search_query=search_query)
        return jsonify({"success": True, "generations": generations}), 200
    except Exception as e:
        logger.error(f"Error in api_get_generations: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/generation/<int:generation_id>', methods=['GET'])
def api_get_generation(generation_id):
    """
    Retrieve single generation record and its FAQs as JSON.
    """
    try:
        generation = get_generation(generation_id)
        if not generation:
            return jsonify({"success": False, "error": "Generation not found"}), 404
        return jsonify({"success": True, "generation": generation}), 200
    except Exception as e:
        logger.error(f"Error in api_get_generation: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/generation/<int:generation_id>/title', methods=['PUT'])
def api_update_title(generation_id):
    """
    Update title of a specific generation.
    """
    data = request.get_json(silent=True) or {}
    new_title = str(data.get('title', '')).strip()

    if not new_title:
        return jsonify({"success": False, "error": "Title cannot be empty."}), 400

    try:
        success = update_generation_title(generation_id, new_title)
        if not success:
            return jsonify({"success": False, "error": "Generation not found or title not updated."}), 404
        return jsonify({"success": True, "message": "Title updated successfully."}), 200
    except Exception as e:
        logger.error(f"Error in api_update_title: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/faq/<int:faq_id>', methods=['PUT'])
def api_update_faq(faq_id):
    """
    Update question, answer, or category of a single FAQ.
    """
    data = request.get_json(silent=True) or {}
    question = str(data.get('question', '')).strip()
    answer = str(data.get('answer', '')).strip()
    category = str(data.get('category', 'General')).strip()

    if not question or not answer:
        return jsonify({"success": False, "error": "Both question and answer are required."}), 400

    try:
        success = update_faq(faq_id, question, answer, category)
        if not success:
            return jsonify({"success": False, "error": "FAQ item not found or not modified."}), 404
        return jsonify({"success": True, "message": "FAQ updated successfully."}), 200
    except Exception as e:
        logger.error(f"Error in api_update_faq: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/faq/<int:faq_id>', methods=['DELETE'])
def api_delete_faq(faq_id):
    """
    Delete a single FAQ item.
    """
    try:
        success = delete_faq(faq_id)
        if not success:
            return jsonify({"success": False, "error": "FAQ not found or could not be deleted."}), 404
        return jsonify({"success": True, "message": "FAQ deleted successfully."}), 200
    except Exception as e:
        logger.error(f"Error in api_delete_faq: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/generation/<int:generation_id>', methods=['DELETE'])
def api_delete_generation(generation_id):
    """
    Delete an entire generation and all associated FAQs.
    """
    try:
        success = delete_generation(generation_id)
        if not success:
            return jsonify({"success": False, "error": "Generation could not be deleted."}), 404
        return jsonify({"success": True, "message": "Generation deleted successfully."}), 200
    except Exception as e:
        logger.error(f"Error in api_delete_generation: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def api_stats():
    """
    Retrieve application metrics.
    """
    try:
        stats = get_stats()
        return jsonify({"success": True, "stats": stats}), 200
    except Exception as e:
        logger.error(f"Error in api_stats: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "stats": {'total_faqs': 0, 'total_generations': 0, 'total_documents': 0}
        }), 500


@app.route('/api/export/<int:generation_id>/<format_type>', methods=['GET'])
def api_export(generation_id, format_type):
    """
    Export FAQs in TXT, CSV, or PDF formats.
    """
    format_type = format_type.lower()
    if format_type not in ['txt', 'csv', 'pdf']:
        return jsonify({"success": False, "error": "Invalid export format. Must be 'txt', 'csv', or 'pdf'."}), 400

    try:
        generation = get_generation(generation_id)
        if not generation:
            return jsonify({"success": False, "error": "Generation not found"}), 404

        title = generation.get('title', f"FAQ_Generation_{generation_id}")
        faqs = generation.get('faqs', [])

        safe_slug = "".join([c if c.isalnum() or c in (' ', '-', '_') else '' for c in title]).strip().replace(' ', '_')
        if not safe_slug:
            safe_slug = f"faq_{generation_id}"

        if format_type == 'txt':
            content = export_txt(title, faqs)
            buffer = io.BytesIO(content.encode('utf-8'))
            return send_file(
                buffer,
                mimetype='text/plain; charset=utf-8',
                as_attachment=True,
                download_name=f"{safe_slug}.txt"
            )

        elif format_type == 'csv':
            content = export_csv(title, faqs)
            buffer = io.BytesIO(content.encode('utf-8-sig'))
            return send_file(
                buffer,
                mimetype='text/csv; charset=utf-8',
                as_attachment=True,
                download_name=f"{safe_slug}.csv"
            )

        elif format_type == 'pdf':
            pdf_bytes = export_pdf(title, faqs)
            buffer = io.BytesIO(pdf_bytes)
            return send_file(
                buffer,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=f"{safe_slug}.pdf"
            )

    except Exception as e:
        logger.error(f"Error exporting generation #{generation_id} as {format_type}: {e}")
        return jsonify({"success": False, "error": f"Failed to export FAQs: {str(e)}"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    System health check verifying database and AI configuration.
    """
    # Check Database
    db_ok = False
    try:
        conn = get_db_connection()
        if conn:
            conn.close()
            db_ok = True
    except Exception:
        db_ok = False

    # Check AI configuration
    groq_key = os.getenv('GROQ_API_KEY')
    ai_ok = bool(groq_key and groq_key.strip() and groq_key != 'your_groq_api_key_here')

    overall_status = "healthy" if (db_ok and ai_ok) else "degraded"

    return jsonify({
        "status": overall_status,
        "database": db_ok,
        "ai": ai_ok
    }), 200


# ==========================================
# ERROR HANDLERS
# ==========================================

@app.errorhandler(404)
def not_found_error(error):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "Endpoint not found"}), 404
    return render_template('base.html', content="<div class='container py-5 text-center'><h1>404</h1><p>Page Not Found</p><a href='/' class='btn btn-primary'>Go Home</a></div>"), 404


@app.errorhandler(413)
@app.errorhandler(RequestEntityTooLarge)
def request_entity_too_large(error):
    msg = "Uploaded file exceeds the maximum allowed size of 10 MB."
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": msg}), 413
    flash(msg, "danger")
    return redirect(url_for('generate_page'))


@app.errorhandler(500)
def internal_server_error(error):
    logger.error(f"Internal server error: {error}")
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "Internal server error occurred."}), 500
    return render_template('base.html', content="<div class='container py-5 text-center'><h1>500</h1><p>Internal Server Error</p><a href='/' class='btn btn-primary'>Go Home</a></div>"), 500


# ==========================================
# APPLICATION ENTRYPOINT
# ==========================================

if __name__ == '__main__':
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
