#!/usr/bin/env python3
"""
Minify JavaScript and CSS files for production deployment.

Usage:
    python tools/minify.py           # JS + CSS → static/{js,css}/dist/
    python tools/minify.py --js      # JS only
    python tools/minify.py --css     # CSS only
    python tools/minify.py --inplace # overwrite source files directly

Requires rjsmin (JS) and rcssmin (CSS):
    pip install rjsmin rcssmin       # both in requirements.txt

Output: creates static/js/dist/ and static/css/dist/ with minified copies.
The app serves from dist/ when it exists, falling back to the originals.
"""
import argparse
import os
import re
import sys

JS_SRC_DIR  = os.path.join(os.path.dirname(__file__), "..", "static", "js")
CSS_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "css")

JS_SKIP  = {"socket.io.min.js"}
CSS_SKIP: set = set()


# ── JS minification ──────────────────────────────────────────────────────────

def _rjsmin(source: str) -> str:
    import rjsmin
    return rjsmin.jsmin(source)


def _basic_js(source: str) -> str:
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    source = re.sub(r'(?<![:/])//[^\n]*', '', source)
    source = re.sub(r'[ \t]+', ' ', source)
    source = re.sub(r'\s*([{};,=+\-*/%&|!<>?:()])\s*', r'\1', source)
    source = re.sub(r'\n\s*\n+', '\n', source)
    return source.strip()


def minify_js(source: str) -> str:
    try:
        return _rjsmin(source)
    except ImportError:
        print("  [!] rjsmin not found, using basic JS minifier")
        return _basic_js(source)


# ── CSS minification ─────────────────────────────────────────────────────────

def _rcssmin(source: str) -> str:
    import rcssmin
    return rcssmin.cssmin(source)


def _basic_css(source: str) -> str:
    source = re.sub(r'/\*.*?\*/', '', source, flags=re.DOTALL)
    source = re.sub(r'\s+', ' ', source)
    source = re.sub(r'\s*([{};:,>~+])\s*', r'\1', source)
    source = re.sub(r';\s*}', '}', source)
    return source.strip()


def minify_css(source: str) -> str:
    try:
        return _rcssmin(source)
    except ImportError:
        print("  [!] rcssmin not found, using basic CSS minifier")
        return _basic_css(source)


# ── Runner ───────────────────────────────────────────────────────────────────

def process_dir(src_dir, out_dir_name, ext, skip_set, minify_fn, label):
    src_dir = os.path.realpath(src_dir)
    if out_dir_name == src_dir:
        out_dir = src_dir
    else:
        out_dir = os.path.join(src_dir, "dist")
        os.makedirs(out_dir, exist_ok=True)

    files = [
        f for f in os.listdir(src_dir)
        if f.endswith(ext) and f not in skip_set
        and not os.path.isdir(os.path.join(src_dir, f))
    ]
    if not files:
        print(f"  No {label} files found in {src_dir}")
        return

    print(f"\n  {label} ({src_dir})")
    total_before = total_after = 0
    for filename in sorted(files):
        src_path = os.path.join(src_dir, filename)
        out_path = os.path.join(out_dir, filename)

        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()

        minified = minify_fn(source)

        before = len(source.encode("utf-8"))
        after  = len(minified.encode("utf-8"))
        saving = before - after
        pct    = 100 * saving / before if before else 0

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(minified)

        total_before += before
        total_after  += after
        print(f"  {filename:<32} {before:>8} B -> {after:>8} B  (-{saving:>7} B, {pct:.0f}%)")

    total_saving = total_before - total_after
    total_pct    = 100 * total_saving / total_before if total_before else 0
    print(f"  {'Total':<32} {total_before:>8} B -> {total_after:>8} B  (-{total_saving:>7} B, {total_pct:.0f}%)")


def main():
    parser = argparse.ArgumentParser(description="Minify JS and CSS static assets")
    parser.add_argument("--inplace", action="store_true",
                        help="Overwrite source files instead of writing to dist/")
    parser.add_argument("--js",  action="store_true", help="Minify JS only")
    parser.add_argument("--css", action="store_true", help="Minify CSS only")
    args = parser.parse_args()

    do_js  = args.js  or not args.css
    do_css = args.css or not args.js

    js_out  = os.path.realpath(JS_SRC_DIR)  if args.inplace else None
    css_out = os.path.realpath(CSS_SRC_DIR) if args.inplace else None

    if do_js:
        process_dir(JS_SRC_DIR,  js_out,  ".js",  JS_SKIP,  minify_js,  "JavaScript")
    if do_css:
        process_dir(CSS_SRC_DIR, css_out, ".css", CSS_SKIP, minify_css, "CSS")

    if not args.inplace:
        print("\n  Minified files written to static/js/dist/ and static/css/dist/")


if __name__ == "__main__":
    main()
