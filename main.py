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
    try:
        uvicorn.run("app.main:app", host=host, port=port, reload=reload)
    except KeyboardInterrupt:
        print("\nFRAS Server stopped by user.")
        sys.exit(0)
