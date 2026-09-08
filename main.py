import uvicorn

if __name__ == "__main__":
    print("=" * 65)
    print("  Enterprise Face Recognition Attendance System (FRAS)")
    print("  Starting Uvicorn Server on http://127.0.0.1:8000")
    print("=" * 65)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
