"""Start the app with one command: python -m web  (then open http://127.0.0.1:8000)."""
import argparse
import sys

import uvicorn

from web.app import DEFAULT_OUT_DIR, DEFAULT_REVIEWS_DIR, create_app


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m web", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: this machine only)")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--project", default=None,
                        help="folder name in out/ (default: the first one that holds a findings.json)")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="pipeline output folder (default: out/)")
    parser.add_argument("--reviews", default=DEFAULT_REVIEWS_DIR, help="folder for the review files (default: reviews/)")
    args = parser.parse_args(argv)
    app = create_app(out_dir=args.out, reviews_dir=args.reviews, project=args.project)
    place = app.state.store.locate()
    print("LV-Pruefstand: http://%s:%d  (data: %s, mode: %s; Ctrl+C stops)"
          % (args.host, args.port, place["source"], place["mode"]), flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
