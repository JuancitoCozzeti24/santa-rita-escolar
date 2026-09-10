"""Compatibility launcher for legacy Render service using `python -m app.server`."""
import runpy

if __name__ == "__main__":
    runpy.run_module("server", run_name="__main__")
