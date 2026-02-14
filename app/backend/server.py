#!/usr/bin/env python3
import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer
from threading import Lock
from urllib.parse import parse_qs, urlparse

backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

LOG_PATH = backend_dir / "server.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

from engine import LocalEngine
DEFAULT_USERNAME = "llminabox"
DEFAULT_PASSWORD = "myllm"
PASSWORD_HASH_PREFIX = "pbkdf2$"
PASSWORD_HASH_ITERATIONS = 120000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )
    return (
        f"{PASSWORD_HASH_PREFIX}{PASSWORD_HASH_ITERATIONS}"
        f"${salt.hex()}${digest.hex()}"
    )


def verify_password(stored_password: str, provided_password: str) -> bool:
    if stored_password.startswith(PASSWORD_HASH_PREFIX):
        try:
            _, iterations_str, salt_hex, digest_hex = stored_password.split("$", 3)
            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except (ValueError, TypeError):
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            provided_password.encode("utf-8"),
            salt,
            iterations,
        )
        return computed == expected
    return stored_password == provided_password


def is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False

DEFAULT_MODELS = [
    {
        "id": "low-end-scout",
        "name": "Low-End Scout",
        "profile": "CPU-only · 4-8GB RAM · Fast boot",
        "status": "available",
        "engine": "local",
        "artifact": "models/low-end",
    },
    {
        "id": "field-general",
        "name": "Field General",
        "profile": "Balanced · 8-16GB RAM · General purpose",
        "status": "available",
        "engine": "local",
        "artifact": "models/mid-range",
        "default": True,
    },
    {
        "id": "high-end-atlas",
        "name": "High-End Atlas",
        "profile": "GPU-ready · 16GB+ RAM · Maximum quality",
        "status": "available",
        "engine": "local",
        "artifact": "models/high-end",
    },
]
MODELS = DEFAULT_MODELS.copy()

SESSION = {"authenticated": False, "user": None}
STATE_LOCK = Lock()


@dataclass
class RuntimeState:
    users: dict
    must_change_password: dict
    loaded_models: set
    eula_accepted: bool

    def to_payload(self):
        return {
            "users": self.users,
            "must_change_password": self.must_change_password,
            "loaded_models": sorted(self.loaded_models),
            "eula_accepted": self.eula_accepted,
        }


STATE = RuntimeState(
    users={DEFAULT_USERNAME: hash_password(DEFAULT_PASSWORD)},
    must_change_password={DEFAULT_USERNAME: True},
    loaded_models=set(),
    eula_accepted=False,
)

STATE_PATH = None
LIBRARY_PATH = None
SAVED_CHATS_PATH = None
PERSONAL_FILES_PATH = None
EULA_PATH = None
ENGINE = LocalEngine()


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class LlmBoxHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api_get(parsed)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api_post(parsed.path)
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def handle_api_get(self, parsed):
        path = parsed.path
        if path == "/api/session":
            return json_response(self, build_session_payload())
        if path == "/api/eula":
            return handle_eula(self)
        if path == "/api/models":
            return json_response(self, {"models": build_model_payload()})
        if path == "/api/library":
            return handle_library_list(self, parsed.query)
        if path == "/api/library/file":
            return handle_library_file(self, parsed.query)
        if path == "/api/storage/info":
            return handle_storage_info(self)
        return json_response(self, {"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def handle_api_post(self, path):
        # Handle file upload separately (multipart/form-data, not JSON)
        if path == "/api/upload":
            return handle_file_upload(self)
        
        # For all other POST endpoints, parse JSON payload
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return json_response(
                self,
                {"error": "Invalid JSON payload"},
                status=HTTPStatus.BAD_REQUEST,
            )

        if path == "/api/login":
            return handle_login(self, payload)
        if path == "/api/logout":
            return handle_logout(self)
        if path == "/api/password":
            return handle_password_change(self, payload)
        if path == "/api/models":
            return handle_model_action(self, payload)
        if path == "/api/chat":
            return handle_chat(self, payload)
        if path == "/api/chat/save":
            return handle_save_chat(self, payload)
        if path == "/api/reset-password":
            return handle_reset_password(self)
        if path == "/api/reset-to-defaults":
            return handle_reset_to_defaults(self)
        if path == "/api/reset":
            return handle_reset(self)
        return json_response(self, {"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def handle_login(handler, payload):
    username = payload.get("username")
    password = payload.get("password")
    accepted_eula = is_truthy(payload.get("accept_eula"))
    if not username or not password:
        return json_response(
            handler,
            {"error": "Username and password are required."},
            status=HTTPStatus.BAD_REQUEST,
        )
    with STATE_LOCK:
        if not STATE.eula_accepted and not accepted_eula:
            return json_response(
                handler,
                {"error": "You must accept the EULA before signing in."},
                status=HTTPStatus.BAD_REQUEST,
            )

        stored_password = STATE.users.get(username)
        if stored_password is None or not verify_password(stored_password, password):
            return json_response(
                handler,
                {"error": "Invalid username or password."},
                status=HTTPStatus.UNAUTHORIZED,
            )

        should_save = False
        if not stored_password.startswith(PASSWORD_HASH_PREFIX):
            STATE.users[username] = hash_password(password)
            should_save = True

        if not STATE.eula_accepted:
            STATE.eula_accepted = True
            should_save = True

        if should_save:
            save_state()

    SESSION["authenticated"] = True
    SESSION["user"] = username
    return json_response(handler, build_session_payload())


def handle_logout(handler):
    SESSION["authenticated"] = False
    SESSION["user"] = None
    return json_response(handler, {"authenticated": False})


def handle_password_change(handler, payload):
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    new_password = payload.get("new_password", "").strip()
    if len(new_password) < 6:
        return json_response(
            handler,
            {"error": "Password must be at least 6 characters."},
            status=HTTPStatus.BAD_REQUEST,
        )
    with STATE_LOCK:
        STATE.users[SESSION["user"]] = hash_password(new_password)
        STATE.must_change_password[SESSION["user"]] = False
        save_state()
    return json_response(handler, {"success": True})

def handle_model_action(handler, payload):
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    model_id = payload.get("id")
    action = payload.get("action")
    if model_id is None or action not in {"load", "unload"}:
        return json_response(
            handler,
            {"error": "Invalid model action"},
            status=HTTPStatus.BAD_REQUEST,
        )
    if model_id not in {model["id"] for model in MODELS}:
        return json_response(
            handler,
            {"error": "Unknown model id"},
            status=HTTPStatus.BAD_REQUEST,
        )
    if action == "load":
        with STATE_LOCK:
            STATE.loaded_models.add(model_id)
            ENGINE.load_model(model_id)
            save_state()
    else:
        with STATE_LOCK:
            STATE.loaded_models.discard(model_id)
            ENGINE.unload_model(model_id)
            save_state()
    return json_response(handler, {"models": build_model_payload()})


def handle_chat(handler, payload):
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    message = payload.get("message", "").strip()
    if not message:
        return json_response(
            handler,
            {"error": "Message cannot be empty"},
            status=HTTPStatus.BAD_REQUEST,
        )
    model_id = select_chat_model()
    try:
        reply = ENGINE.reply(model_id, message)
    except ValueError as exc:
        return json_response(
            handler,
            {"error": str(exc)},
            status=HTTPStatus.BAD_REQUEST,
        )
    
    # Find model name for display
    model_name = next(
        (m["name"] for m in MODELS if m["id"] == model_id),
        model_id
    )
    
    return json_response(handler, {
        "reply": reply,
        "model_id": model_id,
        "model_name": model_name
    })


def handle_library_list(handler, query):
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    # Parse type parameter (guides, chats, personal, or server-log)
    params = parse_qs(query) if query else {}
    library_type = params.get("type", ["guides"])[0]
    
    # Handle server log specially
    if library_type == "server-log":
        try:
            if LOG_PATH.exists():
                with LOG_PATH.open("r", encoding="utf-8") as f:
                    # Read last 100 lines
                    lines = f.readlines()
                    tail_lines = lines[-100:] if len(lines) > 100 else lines
                    return json_response(handler, {"log": "".join(tail_lines)})
            else:
                return json_response(handler, {"log": "Server log not available yet."})
        except Exception as e:
            return json_response(handler, {"log": f"Error reading log: {str(e)}"})
    
    library_dir = get_library_dir(library_type)
    if library_dir is None or not library_dir.exists():
        return json_response(handler, {"files": []})
    files = []
    
    # For personal files, show all file types
    if library_type == "personal":
        glob_pattern = "*"
    else:
        glob_pattern = "*.txt"
    
    for entry in sorted(library_dir.glob(glob_pattern), key=lambda x: x.stat().st_mtime, reverse=True):
        if entry.is_file():
            stat = entry.stat()
            file_info = {
                "name": entry.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            }
            
            # For personal files, add file extension info
            if library_type == "personal":
                file_info["extension"] = entry.suffix.lower()
                file_info["clickable"] = entry.suffix.lower() == ".txt"
            else:
                file_info["clickable"] = True
            
            files.append(file_info)
    
    return json_response(handler, {"files": files})


def handle_library_file(handler, query):
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    params = parse_qs(query)
    requested = params.get("name", [""])[0]
    library_type = params.get("type", ["guides"])[0]
    
    if not requested:
        return json_response(
            handler,
            {"error": "File name is required."},
            status=HTTPStatus.BAD_REQUEST,
        )
    library_dir = get_library_dir(library_type)
    if library_dir is None or not library_dir.exists():
        return json_response(
            handler,
            {"error": "Library directory not found."},
            status=HTTPStatus.NOT_FOUND,
        )
    target = (library_dir / requested).resolve()
    if library_dir not in target.parents:
        return json_response(
            handler,
            {"error": "Invalid file path."},
            status=HTTPStatus.BAD_REQUEST,
        )
    if target.suffix.lower() != ".txt" or not target.exists():
        return json_response(
            handler,
            {"error": "File not found."},
            status=HTTPStatus.NOT_FOUND,
        )
    content = target.read_text(encoding="utf-8", errors="replace")
    return json_response(handler, {"name": target.name, "content": content})


def build_model_payload():
    models = []
    for model in MODELS:
        model_id = model["id"]
        status = ENGINE.get_model_status(model_id)
        model_data = {**model, "status": status}
        
        # Include error message if model failed to load
        if status == "error":
            error_msg = ENGINE.get_model_error(model_id)
            model_data["error"] = error_msg
        
        models.append(model_data)
    return models


def build_session_payload():
    with STATE_LOCK:
        eula_accepted = bool(STATE.eula_accepted)
    if not SESSION["authenticated"]:
        return {
            "authenticated": False,
            "user": None,
            "must_change_password": False,
            "eula_accepted": eula_accepted,
        }
    with STATE_LOCK:
        must_change = STATE.must_change_password.get(SESSION["user"], True)
    return {
        "authenticated": True,
        "user": SESSION["user"],
        "must_change_password": must_change,
        "eula_accepted": eula_accepted,
    }


def handle_eula(handler):
    if EULA_PATH is None or not EULA_PATH.exists():
        return json_response(
            handler,
            {"error": "EULA file not found."},
            status=HTTPStatus.NOT_FOUND,
        )
    content = EULA_PATH.read_text(encoding="utf-8", errors="replace")
    return json_response(handler, {"content": content})


def load_state(path):
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Could not load state file: %s. Using defaults.", e)
        return
    
    # Only override if we have valid data; otherwise preserve defaults
    if "users" in payload and payload["users"]:
        STATE.users = payload["users"]
    if "must_change_password" in payload:
        STATE.must_change_password = payload["must_change_password"]
    STATE.loaded_models = set(payload.get("loaded_models", []))
    STATE.eula_accepted = bool(payload.get("eula_accepted", False))
    # Note: Don't sync to ENGINE yet - models will be reloaded on startup


def save_state():
    if STATE_PATH is None:
        return
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(STATE.to_payload(), handle, indent=2, sort_keys=True)


def load_models(path):
    if not path.exists():
        return DEFAULT_MODELS.copy()
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    models = payload.get("models", [])
    return models or DEFAULT_MODELS.copy()


def select_chat_model():
    with STATE_LOCK:
        if STATE.loaded_models:
            return sorted(STATE.loaded_models)[0]
    return next((model["id"] for model in MODELS if model.get("default")), "field-general")


def get_library_dir(library_type="guides"):
    if library_type == "chats":
        return SAVED_CHATS_PATH
    elif library_type == "personal":
        return PERSONAL_FILES_PATH
    return LIBRARY_PATH


def handle_save_chat(handler, payload):
    """Save a chat conversation to a text file."""
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    
    messages = payload.get("messages", [])
    if not messages:
        return json_response(
            handler,
            {"error": "No messages to save."},
            status=HTTPStatus.BAD_REQUEST,
        )
    
    # Ensure saved chats directory exists
    if SAVED_CHATS_PATH is None:
        return json_response(
            handler,
            {"error": "Saved chats directory not configured."},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    
    SAVED_CHATS_PATH.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"Chat_{timestamp}.txt"
    filepath = SAVED_CHATS_PATH / filename
    
    # Format chat content
    content_lines = ["LLM-in-a-Box Chat Session", f"Saved: {timestamp}", "=" * 60, ""]
    for msg in messages:
        author = msg.get("author", "Unknown")
        text = msg.get("message", "")
        content_lines.append(f"{author}:")
        content_lines.append(text)
        content_lines.append("")
    
    content = "\n".join(content_lines)
    filepath.write_text(content, encoding="utf-8")
    
    return json_response(handler, {"success": True, "filename": filename})


def handle_storage_info(handler):
    """Get disk space information for the drive."""
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    
    import shutil
    try:
        # Get disk usage for the repository root
        repo_root = Path(__file__).resolve().parents[2]
        usage = shutil.disk_usage(repo_root)
        
        total_bytes = usage.total
        used_bytes = usage.used
        free_bytes = usage.free
        
        # Convert to GB or MB
        free_gb = free_bytes / (1024 ** 3)
        total_gb = total_bytes / (1024 ** 3)
        
        if free_gb >= 1:
            free_display = f"{free_gb:.2f} GB"
            total_display = f"{total_gb:.2f} GB"
        else:
            free_mb = free_bytes / (1024 ** 2)
            total_mb = total_bytes / (1024 ** 2)
            free_display = f"{free_mb:.2f} MB"
            total_display = f"{total_mb:.2f} MB"
        
        return json_response(handler, {
            "free_bytes": free_bytes,
            "total_bytes": total_bytes,
            "used_bytes": used_bytes,
            "free_display": free_display,
            "total_display": total_display,
        })
    except Exception as e:
        return json_response(
            handler,
            {"error": f"Unable to get storage info: {str(e)}"},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


def handle_file_upload(handler):
    """Handle file upload to Personal Files directory."""
    logger.debug("Upload request received")
    
    if not SESSION["authenticated"]:
        logger.debug("Not authenticated")
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    
    if PERSONAL_FILES_PATH is None:
        logger.debug("Personal files path not configured")
        return json_response(
            handler,
            {"error": "Personal files directory not configured."},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
    
    PERSONAL_FILES_PATH.mkdir(parents=True, exist_ok=True)
    
    import shutil
    import re
    
    content_type = handler.headers.get('Content-Type', '')
    logger.debug("Content-Type: %s", content_type)
    
    if not content_type.startswith('multipart/form-data'):
        logger.debug("Invalid content type")
        return json_response(
            handler,
            {"error": "Invalid content type. Expected multipart/form-data."},
            status=HTTPStatus.BAD_REQUEST,
        )
    
    try:
        # Extract boundary from Content-Type header
        boundary_match = re.search(r'boundary=([^;]+)', content_type)
        if not boundary_match:
            logger.debug("No boundary found")
            return json_response(
                handler,
                {"error": "No boundary found in Content-Type."},
                status=HTTPStatus.BAD_REQUEST,
            )
        
        boundary = boundary_match.group(1).strip('"')
        logger.debug("Boundary: %s", boundary)
        boundary_bytes = ('--' + boundary).encode()
        
        # Read the entire request body
        content_length = int(handler.headers.get('Content-Length', 0))
        logger.debug("Content-Length: %s", content_length)
        body = handler.rfile.read(content_length)
        logger.debug("Read %s bytes", len(body))
        
        # Split by boundary
        parts = body.split(boundary_bytes)
        logger.debug("Found %s parts", len(parts))
        
        filename = None
        file_data = None
        
        # Parse parts to find the file
        for i, part in enumerate(parts):
            logger.debug("Processing part %s, length %s", i, len(part))
            if b'Content-Disposition' in part and b'filename=' in part:
                logger.debug("Found file part")
                # Extract filename
                filename_match = re.search(rb'filename="([^"]+)"', part)
                if filename_match:
                    filename = filename_match.group(1).decode('utf-8', errors='replace')
                    logger.debug("Filename: %s", filename)
                
                # Extract file data (everything after the headers)
                # Headers end with \r\n\r\n
                header_end = part.find(b'\r\n\r\n')
                if header_end != -1:
                    file_data = part[header_end + 4:]
                    # Remove trailing \r\n if present
                    if file_data.endswith(b'\r\n'):
                        file_data = file_data[:-2]
                    logger.debug("File data length: %s", len(file_data))
                break
        
        if not filename or file_data is None:
            logger.debug("No file found in request")
            return json_response(
                handler,
                {"error": "No file provided or invalid form data."},
                status=HTTPStatus.BAD_REQUEST,
            )
        
        file_size = len(file_data)
        logger.debug("File size: %s bytes", file_size)
        
        # Check disk space
        repo_root = Path(__file__).resolve().parents[2]
        usage = shutil.disk_usage(repo_root)
        free_bytes = usage.free
        
        # Calculate required space (file size + 15% reserved)
        required_bytes = file_size * 1.15
        logger.debug("Required: %s, Available: %s", required_bytes, free_bytes)
        
        if required_bytes > free_bytes:
            free_mb = free_bytes / (1024 ** 2)
            required_mb = required_bytes / (1024 ** 2)
            logger.debug("Insufficient space")
            return json_response(
                handler,
                {"error": f"Insufficient space. Need {required_mb:.2f} MB but only {free_mb:.2f} MB available (including 15% reserve)."},
                status=HTTPStatus.INSUFFICIENT_STORAGE,
            )
        
        # Sanitize filename
        import os
        filename = os.path.basename(filename)
        logger.debug("Sanitized filename: %s", filename)
        
        if not filename or filename.startswith('.') or '/' in filename or '\\' in filename:
            logger.debug("Invalid filename")
            return json_response(
                handler,
                {"error": "Invalid filename."},
                status=HTTPStatus.BAD_REQUEST,
            )
        
        # Save file
        filepath = PERSONAL_FILES_PATH / filename
        logger.debug("Filepath: %s", filepath)
        
        # Check if file already exists
        if filepath.exists():
            logger.debug("File already exists")
            return json_response(
                handler,
                {"error": f"File '{filename}' already exists. Please rename the file or delete the existing one first."},
                status=HTTPStatus.CONFLICT,
            )
        
        with filepath.open('wb') as f:
            f.write(file_data)
        
        logger.info("File saved successfully: %s", filepath)
        return json_response(handler, {"success": True, "filename": filename})
        
    except Exception as e:
        logger.exception("Upload failed")
        return json_response(
            handler,
            {"error": f"Upload failed: {str(e)}"},
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )


def handle_reset_password(handler):
    """Reset password to default."""
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    
    # Reset password to default
    with STATE_LOCK:
        STATE.users[DEFAULT_USERNAME] = hash_password(DEFAULT_PASSWORD)
        STATE.must_change_password[DEFAULT_USERNAME] = True
        save_state()
    
    # Reset session
    SESSION["authenticated"] = False
    SESSION["user"] = None
    
    return json_response(handler, {"success": True, "message": "Password reset."})


def handle_reset_to_defaults(handler):
    """Reset all settings to defaults AND delete all saved files/chats."""
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    
    # Delete all saved chats
    if SAVED_CHATS_PATH and SAVED_CHATS_PATH.exists():
        try:
            import shutil
            for item in SAVED_CHATS_PATH.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        except Exception as e:
            logger.error("Error cleaning saved chats: %s", e)
    
    # Delete all personal files
    if PERSONAL_FILES_PATH and PERSONAL_FILES_PATH.exists():
        try:
            import shutil
            for item in PERSONAL_FILES_PATH.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
        except Exception as e:
            logger.error("Error cleaning personal files: %s", e)
    
    # Delete state file to reset to defaults
    if STATE_PATH and STATE_PATH.exists():
        try:
            STATE_PATH.unlink()
        except OSError:
            pass
    
    # Reset session
    SESSION["authenticated"] = False
    SESSION["user"] = None
    
    # Reset in-memory state
    with STATE_LOCK:
        global STATE
        STATE = RuntimeState(
            users={DEFAULT_USERNAME: hash_password(DEFAULT_PASSWORD)},
            must_change_password={DEFAULT_USERNAME: True},
            loaded_models=set(),
            eula_accepted=False,
        )
        save_state()
    
    return json_response(handler, {"success": True, "message": "All settings and files reset."})


def handle_reset(handler):
    """Reset all settings to defaults and restart the server."""
    if not SESSION["authenticated"]:
        return json_response(
            handler,
            {"error": "Unauthorized"},
            status=HTTPStatus.UNAUTHORIZED,
        )
    
    # Delete state file to reset to defaults
    if STATE_PATH and STATE_PATH.exists():
        try:
            STATE_PATH.unlink()
        except OSError:
            pass
    
    # Reset session
    SESSION["authenticated"] = False
    SESSION["user"] = None
    
    # Reset in-memory state
    with STATE_LOCK:
        global STATE
        STATE = RuntimeState(
            users={DEFAULT_USERNAME: hash_password(DEFAULT_PASSWORD)},
            must_change_password={DEFAULT_USERNAME: True},
            loaded_models=set(),
            eula_accepted=False,
        )
        save_state()
    
    return json_response(handler, {"success": True, "message": "Settings reset. Server restarting..."})


def main():
    repo_root = Path(__file__).resolve().parents[2]
    
    parser = argparse.ArgumentParser(description="LLM in a Box local server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--static-dir",
        default="app/frontend",
        help="Directory to serve frontend assets from",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory to persist backend state",
    )
    parser.add_argument(
        "--models-config",
        default="app/backend/models.json",
        help="Path to model catalog configuration",
    )
    parser.add_argument(
        "--library-dir",
        default="Survival Guides",
        help="Directory containing offline survival guides",
    )
    args = parser.parse_args()

    global STATE_PATH
    STATE_PATH = Path(args.data_dir) / "state.json"
    with STATE_LOCK:
        load_state(STATE_PATH)
        save_state()

    global MODELS
    MODELS = load_models(Path(args.models_config))
    ENGINE.set_model_catalog(MODELS)

    # Reload models that were previously loaded before shutdown
    if STATE.loaded_models:
        models_to_reload = STATE.loaded_models.copy()
        STATE.loaded_models.clear()  # Clear and repopulate based on actual load results
        
        logger.info("%s", "=" * 60)
        logger.info("Reloading %s model(s) from previous session...", len(models_to_reload))
        logger.info("%s", "=" * 60)
        for model_id in models_to_reload:
            model = next((m for m in MODELS if m.get("id") == model_id), None)
            if model:
                logger.info("Loading %s...", model.get("name", model_id))
                try:
                    ENGINE.load_model(model_id)
                    STATE.loaded_models.add(model_id)  # Only add if load succeeds
                    logger.info("✓ %s loaded successfully", model.get("name", model_id))
                except Exception as e:
                    logger.error("✗ Failed to reload %s: %s", model_id, e)
            else:
                logger.warning("⚠ Skipping unknown model: %s", model_id)
        
        # Save updated state with only successfully loaded models
        with STATE_LOCK:
            save_state()
        logger.info("%s", "=" * 60)

    global LIBRARY_PATH, SAVED_CHATS_PATH, PERSONAL_FILES_PATH, EULA_PATH
    LIBRARY_PATH = Path(args.library_dir).resolve()
    SAVED_CHATS_PATH = (repo_root / "Saved Chats").resolve()
    SAVED_CHATS_PATH.mkdir(parents=True, exist_ok=True)
    PERSONAL_FILES_PATH = (repo_root / "Personal Files").resolve()
    PERSONAL_FILES_PATH.mkdir(parents=True, exist_ok=True)
    EULA_PATH = (repo_root / "EULA.txt").resolve()

    handler = lambda *handler_args, **handler_kwargs: LlmBoxHandler(
        *handler_args, directory=args.static_dir, **handler_kwargs
    )

    with ThreadingTCPServer(("", args.port), handler) as server:
        url = f"http://127.0.0.1:{args.port}"
        logger.info("\n%s\n#%s#\n#%s#\n#%s#\n#%s#\n%s\n", "#" * 60, " " * 58, "  LLM-in-a-Box is READY!".center(58), f"  {url}".center(58), " " * 58, "#" * 60)
        
        if STATE.loaded_models:
            logger.info("Models loaded: %s", ", ".join(STATE.loaded_models))
        
        server.serve_forever()


if __name__ == "__main__":
    main()
