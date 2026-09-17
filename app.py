import os
import pymysql
from flask import Flask, jsonify
from config import Config
from models import db
from routes.api import api_bp
from routes.views import views_bp


def create_app(config_class=Config):
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_object(config_class)

    # If DB_TYPE is mysql, verify connection before initializing SQLAlchemy
    if app.config.get("DB_TYPE") == "mysql" and not app.config.get("TESTING"):
        can_connect_mysql = False
        try:
            conn = pymysql.connect(
                host=app.config.get("DB_HOST", "localhost"),
                port=int(app.config.get("DB_PORT", 3306)),
                user=app.config.get("DB_USER", "root"),
                password=app.config.get("DB_PASSWORD", ""),
                database=app.config.get("DB_NAME", "clinic_db"),
                charset="utf8mb4",
                connect_timeout=3,
            )
            conn.close()
            can_connect_mysql = True
            print(f"[Database] Connected to MySQL database '{app.config.get('DB_NAME')}' at {app.config.get('DB_HOST')}:{app.config.get('DB_PORT')}.")
        except Exception as err:
            print(f"[Database Notice] MySQL connection not yet available: {err}")
            print("[Database Notice] Falling back to SQLite clinic.db. Set DB_PASSWORD in .env to use MySQL.")
            app.config["SQLALCHEMY_DATABASE_URI"] = Config.get_database_uri(force_sqlite=True)
            app.config["DB_TYPE"] = "sqlite"

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    @app.route("/health")
    def health_check():
        db_connected = False
        db_engine = "unknown"
        try:
            with app.app_context():
                db.session.execute(db.text("SELECT 1"))
                db_connected = True
                db_engine = db.engine.name
        except Exception as e:
            db_engine = f"error: {str(e)}"

        return jsonify({
            "status": "healthy" if db_connected else "degraded",
            "database_connected": db_connected,
            "database_engine": db_engine,
        })

    # Error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return jsonify({"success": False, "error": "Endpoint or resource not found."}), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify({"success": False, "error": "Internal server error occurred."}), 500

    # Auto create tables if needed
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            if not app.config.get("TESTING"):
                print(f"[Notice] Table creation error: {e}")

    return app


if __name__ == "__main__":
    app = create_app()
    print("================================================================")
    print("  CareFlow Clinic Front-Desk Booking & Fair Cancellation System")
    print("  Server running at: http://127.0.0.1:5000")
    print("================================================================")
    app.run(host="127.0.0.1", port=5000, debug=True)
