import os
import sys
import uvicorn
from app.config import ENVIRONMENT

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = ENVIRONMENT == "development"

    print("=" * 65)
    print("  Enterprise Face Recognition Attendance System (FRAS)")
    print(f"  Starting Server on http://{host}:{port} (Environment: {ENVIRONMENT})")
    print("=" * 65)

    uvicorn_kwargs = {
        "app": "app.main:app",
        "host": host,
        "port": port,
        "reload": reload,
    }
    if reload:
        # Avoid file watcher loop on database writes and ONNX binaries
        uvicorn_kwargs["reload_dirs"] = ["app"]
        uvicorn_kwargs["reload_excludes"] = ["*.db", "*.db-*", "data/*", "models/*", ".git/*"]

    try:
        uvicorn.run(**uvicorn_kwargs)
    except KeyboardInterrupt:
        print("\nFRAS Server stopped by user.")
        sys.exit(0)
    except OSError as e:
        print(f"\n[ERROR] Server startup failed: {e}")
        print(f"  Port {port} may already be in use. You can change PORT=8001 in your .env file.")
        sys.exit(1)
