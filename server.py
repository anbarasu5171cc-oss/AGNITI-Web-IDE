import json
import mimetypes
import subprocess
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


# ============================================================
# AGNITI SERVER CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
COMPILER_DIR = BASE_DIR / "compiler"

HOST = "127.0.0.1"
PORT = 8001

# Allow the existing compiler files to be imported.
sys.path.insert(0, str(COMPILER_DIR))

from lexer import Lexer
from parser import Parser
from code_generator import CodeGenerator


# ============================================================
# AGNITI COMPILER
# ============================================================

def compile_agniti(source):
    """
    Existing AGNITI compiler pipeline:

    AGNITI Source
        ↓
    Lexer
        ↓
    Parser
        ↓
    AST
        ↓
    Code Generator
        ↓
    Python Code
    """

    tokens = Lexer(source).tokenize()

    ast = Parser(tokens).parse()

    generated_python = CodeGenerator(ast).generate()

    return generated_python


# ============================================================
# PYTHON EXECUTION
# ============================================================

def execute_python(generated_python):
    """
    Execute generated Python on the backend.

    Generated Python is never returned to the frontend.
    """

    temporary_file = None

    start_time = time.perf_counter()

    try:

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            encoding="utf-8",
            delete=False,
            dir=BASE_DIR
        ) as file:

            temporary_file = Path(file.name)

            file.write(generated_python)


        process = subprocess.run(
            [
                sys.executable,
                str(temporary_file)
            ],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30
        )


        elapsed_ms = (
            time.perf_counter() - start_time
        ) * 1000


        return {
            "output": process.stdout,
            "error": process.stderr,
            "returncode": process.returncode,
            "runtime_ms": elapsed_ms
        }


    except subprocess.TimeoutExpired:

        elapsed_ms = (
            time.perf_counter() - start_time
        ) * 1000

        return {
            "output": "",
            "error": (
                "Program stopped because "
                "the execution time limit was exceeded."
            ),
            "returncode": 124,
            "runtime_ms": elapsed_ms
        }


    finally:

        if temporary_file is not None:

            try:
                temporary_file.unlink(
                    missing_ok=True
                )

            except Exception:
                pass


# ============================================================
# JSON RESPONSE
# ============================================================

def send_json(handler, status_code, data):

    response = json.dumps(
        data,
        ensure_ascii=False
    ).encode("utf-8")


    handler.send_response(
        status_code
    )

    handler.send_header(
        "Content-Type",
        "application/json; charset=utf-8"
    )

    handler.send_header(
        "Content-Length",
        str(len(response))
    )

    handler.send_header(
        "Cache-Control",
        "no-store"
    )

    handler.end_headers()

    handler.wfile.write(
        response
    )


# ============================================================
# FILE SERVER + API
# ============================================================

class AGNITIHandler(BaseHTTPRequestHandler):

    # --------------------------------------------------------
    # Reduce default HTTP logging
    # --------------------------------------------------------

    def log_message(self, format, *args):

        print(
            f"[{self.log_date_time_string()}] "
            f"{format % args}"
        )


    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(self):

        parsed_url = urlparse(
            self.path
        )

        path = parsed_url.path


        # ====================================================
        # BACKEND HEALTH CHECK
        # ====================================================

        if path == "/api/health":

            send_json(
                self,
                200,
                {
                    "status": "ok",
                    "service": "AGNITI Backend",
                    "compiler": "Python"
                }
            )

            return


        # ====================================================
        # FRONTEND FILES
        # ====================================================

        requested_path = unquote(
            path.lstrip("/")
        )


        if not requested_path:

            requested_path = "index.html"


        requested_file = (
            BASE_DIR / requested_path
        ).resolve()


        # Prevent path traversal.
        try:

            requested_file.relative_to(
                BASE_DIR
            )

        except ValueError:

            self.send_error(
                403,
                "Forbidden"
            )

            return


        if not requested_file.is_file():

            self.send_error(
                404,
                "File not found"
            )

            return


        try:

            content = requested_file.read_bytes()

        except Exception:

            self.send_error(
                500,
                "Unable to read file"
            )

            return


        content_type, _ = mimetypes.guess_type(
            str(requested_file)
        )


        if content_type is None:

            content_type = (
                "application/octet-stream"
            )


        self.send_response(200)

        self.send_header(
            "Content-Type",
            content_type
        )

        self.send_header(
            "Content-Length",
            str(len(content))
        )

        self.end_headers()

        self.wfile.write(
            content
        )


    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def do_POST(self):

        parsed_url = urlparse(
            self.path
        )

        path = parsed_url.path


        # ====================================================
        # RUN AGNITI PROGRAM
        # ====================================================

        if path != "/api/run":

            send_json(
                self,
                404,
                {
                    "success": False,
                    "error": "API endpoint not found."
                }
            )

            return


        # ====================================================
        # READ REQUEST
        # ====================================================

        try:

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )


            if content_length <= 0:

                send_json(
                    self,
                    400,
                    {
                        "success": False,
                        "error": "Empty request."
                    }
                )

                return


            if content_length > 1_000_000:

                send_json(
                    self,
                    413,
                    {
                        "success": False,
                        "error":
                            "AGNITI program is too large."
                    }
                )

                return


            request_body = self.rfile.read(
                content_length
            )


            data = json.loads(
                request_body.decode(
                    "utf-8"
                )
            )


            source = data.get(
                "source",
                ""
            )


            if not isinstance(
                source,
                str
            ):

                send_json(
                    self,
                    400,
                    {
                        "success": False,
                        "error":
                            "Invalid AGNITI source."
                    }
                )

                return


            if not source.strip():

                send_json(
                    self,
                    400,
                    {
                        "success": False,
                        "error":
                            "Write an AGNITI program before running."
                    }
                )

                return


        except json.JSONDecodeError:

            send_json(
                self,
                400,
                {
                    "success": False,
                    "error":
                        "Invalid JSON request."
                }
            )

            return


        except Exception as error:

            send_json(
                self,
                400,
                {
                    "success": False,
                    "error":
                        str(error)
                }
            )

            return


        # ====================================================
        # AGNITI → PYTHON
        # ====================================================

        try:

            generated_python = (
                compile_agniti(
                    source
                )
            )


        except Exception as error:

            send_json(
                self,
                400,
                {
                    "success": False,
                    "stage": "compile",
                    "error": str(error)
                }
            )

            return


        # ====================================================
        # PYTHON BACKEND EXECUTION
        # ====================================================

        try:

            result = execute_python(
                generated_python
            )


        except Exception as error:

            send_json(
                self,
                500,
                {
                    "success": False,
                    "stage": "runtime",
                    "error": str(error)
                }
            )

            return


        # ====================================================
        # FRONTEND RESPONSE
        #
        # IMPORTANT:
        #
        # generated_python is NOT included here.
        #
        # Frontend receives only:
        # - success
        # - output
        # - error
        # - runtime
        # ====================================================

        success = (
            result["returncode"] == 0
        )


        send_json(
            self,
            200,
            {
                "success": success,
                "stage": "runtime",
                "output": result["output"],
                "error": result["error"],
                "runtime_ms": round(
                    result["runtime_ms"],
                    2
                )
            }
        )


# ============================================================
# START SERVER
# ============================================================

def main():

    server = ThreadingHTTPServer(
        (
            HOST,
            PORT
        ),
        AGNITIHandler
    )


    print()
    print("=" * 60)
    print("AGNITI WEB IDE BACKEND")
    print("=" * 60)
    print()
    print(
        f"Frontend + Backend:"
        f" http://{HOST}:{PORT}"
    )
    print()
    print(
        "AGNITI → Lexer → Parser → AST → "
        "Python Code Generator → Python Runtime"
    )
    print()
    print(
        "Generated Python is backend-only."
    )
    print(
        "Generated Python is NOT sent to frontend."
    )
    print()
    print(
        "Press CTRL+C to stop the server."
    )
    print("=" * 60)
    print()


    try:

        server.serve_forever()

    except KeyboardInterrupt:

        print()
        print("Stopping AGNITI backend...")


    finally:

        server.server_close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()