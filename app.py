from flask import Flask, render_template, request, redirect, url_for
import json
import os
from datetime import datetime
import calendar
from collections import defaultdict
from werkzeug.utils import secure_filename

app = Flask(__name__)

DATA_FILE = "entries.json"

UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def load_entries():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            entries = json.load(f)
        except json.JSONDecodeError:
            return []

    # Ensure all entries have the new keys
    for e in entries:
        e.setdefault("category", "Art")   # generic default
        e.setdefault("subcategory", "")   # e.g. "Spiritual"
        e.setdefault("tags", [])

        # Dreamboard-specific fields (all optional)
        e.setdefault("dream_theme", "")          # e.g. "Career", "Travel"
        e.setdefault("dream_priority", "")       # "High", "Medium", "Low"
        e.setdefault("dream_target_date", "")    # "2025-12-31"
        e.setdefault("dream_progress", 0)        # integer 0–100

    return entries


def save_entries(entries):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def next_id(entries):
    if not entries:
        return 1
    existing_ids = [e.get("id", 0) for e in entries]
    return max(existing_ids) + 1


def compute_dream_entries(entries):
    dream_keywords = {"dream", "dreams", "goal", "goals", "manifest", "manifestation"}
    result = []
    for e in entries:
        cat = (e.get("category") or "").lower()
        tags = [t.lower() for t in e.get("tags", [])]

        if cat in {"goal", "goals", "dreams", "dreamboard"}:
            result.append(e)
        elif dream_keywords.intersection(tags):
            result.append(e)

    return sorted(result, key=lambda e: e.get("date", ""), reverse=True)


@app.route("/")
def home():
    entries = load_entries()

    # Simple friendly daily message
    today_str = datetime.today().strftime("%A, %B %d")
    daily_message = (
        f"Today is {today_str}. Even one tiny note or dream update keeps your gallery alive. 🌱"
    )

    # Categories & subcategories for the sidebar + home collections
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "home.html",
        current_page="home",
        entries=entries,
        daily_message=daily_message,
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
    )


@app.route("/gallery")
def index():
    entries = load_entries()

    # --- Split into normal vs dream entries ---
    dream_entries = compute_dream_entries(entries)  # already sorted (newest first)
    regular_entries = [e for e in entries if e not in dream_entries]

    # Sort regular entries (newest first)
    regular_entries_sorted = sorted(
        regular_entries,
        key=lambda e: e.get("date", ""),
        reverse=True,
    )

    # Latest 3 daily reflections
    reflections_all = [
        e for e in entries
        if e.get("category") == "Life diary"
        and e.get("subcategory") == "Daily reflection"
    ]
    featured_reflections = sorted(
        reflections_all,
        key=lambda e: e.get("date", ""),
        reverse=True,
    )[:3]

    # Latest 3 dreams/goals
    featured_dreams = dream_entries[:3]

    # Sidebar data (stays the same, based on ALL entries)
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "index.html",
        current_page="index",
        entries=regular_entries_sorted,
        dream_entries=dream_entries,
        featured_reflections=featured_reflections,
        featured_dreams=featured_dreams,
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=None,
        current_subcategory=None,
        search_query=None,
    )


@app.route("/timeline")
def timeline():
    entries = load_entries()

    # Which collection are we filtering by? (optional)
    current_category = request.args.get("category")

    # Entries to show on the timeline (respect the filter if present)
    if current_category:
        scoped_entries = [
            e for e in entries
            if e.get("category", "").lower() == current_category.lower()
        ]
    else:
        scoped_entries = entries

    # Only entries that have a date
    dated_entries = [e for e in scoped_entries if e.get("date")]

    # Sort newest → oldest (YYYY-MM-DD works as a string sort)
    dated_entries = sorted(
        dated_entries,
        key=lambda e: e.get("date", ""),
        reverse=True,
    )

    # Group into {year: {month: [entries...]}}
    grouped = defaultdict(lambda: defaultdict(list))
    for e in dated_entries:
        d = e.get("date")
        if not d or len(d) < 7:
            continue
        year = d[:4]
        month = d[5:7]  # "01".."12"
        grouped[year][month].append(e)

    # Build a list that is easy for Jinja to loop over
    timeline_years = []
    for year in sorted(grouped.keys(), reverse=True):
        months = grouped[year]
        month_blocks = []

        for month in sorted(months.keys(), reverse=True):
            month_num = int(month)
            month_name = calendar.month_name[month_num]
            month_blocks.append({
                "month": month,
                "month_name": month_name,
                "entries": months[month],
            })

        timeline_years.append({
            "year": year,
            "months": month_blocks,
        })

    # Sidebar + filter options should always see ALL collections/themes
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "timeline.html",
        current_page="timeline",
        timeline_years=timeline_years,
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=current_category,
    )


@app.route("/category/<name>")
def category_view(name):
    entries = load_entries()
    filtered = [e for e in entries if e.get("category", "").lower() == name.lower()]
    entries_sorted = sorted(filtered, key=lambda e: e.get("date", ""), reverse=True) if filtered else []

    # categories + subcategories for sidebar
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    # build mapping { "Art": ["Spiritual", "Nature"], ... }
    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "index.html",
        current_page="index",
        entries=entries_sorted,
        dream_entries=[],
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=name,
        current_subcategory=None,
        search_query=None,
    )


@app.route("/subcategory/<name>")
def subcategory_view(name):
    entries = load_entries()
    filtered = [e for e in entries if e.get("subcategory", "").lower() == name.lower()]
    entries_sorted = sorted(filtered, key=lambda e: e.get("date", ""), reverse=True) if filtered else []

    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "index.html",
        current_page="index",
        entries=entries_sorted,
        dream_entries=[],
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=None,
        current_subcategory=name,
        search_query=None,
    )


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    entries = load_entries()

    # If no query, just go back to all entries
    if not query:
        return redirect(url_for("index"))

    q = query.lower()

    # Find entries where the query appears in title/notes/tags/etc.
    def matches(e):
        text_bits = [
            e.get("title", ""),
            e.get("notes", ""),
            e.get("mood", ""),
            e.get("category", ""),
            e.get("subcategory", ""),
            " ".join(e.get("tags", [])),
        ]
        haystack = " ".join(text_bits).lower()
        return q in haystack

    filtered = [e for e in entries if matches(e)]
    entries_sorted = sorted(filtered, key=lambda e: e.get("date", ""), reverse=True)

    # Build sidebar data
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "index.html",
        current_page="index",
        entries=entries_sorted,
        dream_entries=[],
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=None,
        current_subcategory=None,
        search_query=query,
    )


@app.route("/new", methods=["GET", "POST"])
def new_entry():
    entries = load_entries()

    if request.method == "POST":
        image_path = ""

        if "image_file" in request.files:
            file = request.files["image_file"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(save_path)
                image_path = os.path.join("uploads", filename)

        entry_id = next_id(entries)

        raw_tags = request.form.get("tags", "")
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

        entry = {
            "id": entry_id,
            "title": request.form["title"],
            "date": request.form.get("date") or datetime.today().strftime("%Y-%m-%d"),
            "mood": request.form.get("mood", ""),
            "category": request.form.get("category", "Art"),
            "subcategory": request.form.get("subcategory", ""),
            "image_path": image_path,
            "notes": request.form.get("notes", ""),
            "tags": tags,
            "created_at": datetime.utcnow().isoformat(),

            # NEW dreamboard fields (optional)
            "dream_priority": request.form.get("dream_priority", "").strip(),
            "dream_progress": request.form.get("dream_progress", "").strip(),
            "dream_target_date": request.form.get("dream_target_date", "").strip(),
            "dream_theme": request.form.get("dream_theme", "").strip(),
        }

        entries.append(entry)
        save_entries(entries)
        return redirect(url_for("index"))

    # GET: build suggestion lists from existing entries
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    return render_template(
        "new.html",
        current_page="new_entry",
        categories=categories,
        subcategories=subcategories,
    )


@app.route("/entry/<int:entry_id>")
def entry_detail(entry_id):
    entries = load_entries()
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if not entry:
        return "Entry not found", 404
    return render_template("detail.html", entry=entry)


@app.route("/entry/<int:entry_id>/edit", methods=["GET", "POST"])
def edit_entry(entry_id):
    entries = load_entries()
    entry = next((e for e in entries if e.get("id") == entry_id), None)
    if not entry:
        return "Entry not found", 404

    # ensure keys exist for older entries
    entry.setdefault("category", "Art")
    entry.setdefault("subcategory", "")
    entry.setdefault("tags", [])

    # suggestion lists from ALL entries
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    if request.method == "POST":
        # keep old image by default
        image_path = entry.get("image_path", "")

        # optional new file
        if "image_file" in request.files:
            file = request.files["image_file"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(save_path)
                image_path = os.path.join("uploads", filename)

        raw_tags = request.form.get("tags", "")
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

        entry.update({
            "title": request.form["title"],
            "date": request.form.get("date") or entry.get("date", ""),
            "mood": request.form.get("mood", ""),
            "category": request.form.get("category", "Art"),
            "subcategory": request.form.get("subcategory", ""),
            "image_path": image_path,
            "notes": request.form.get("notes", ""),
            "tags": tags,

            # NEW dreamboard fields
            "dream_priority": request.form.get("dream_priority", "").strip(),
            "dream_progress": request.form.get("dream_progress", "").strip(),
            "dream_target_date": request.form.get("dream_target_date", "").strip(),
            "dream_theme": request.form.get("dream_theme", "").strip(),
        })

        save_entries(entries)
        return redirect(url_for("entry_detail", entry_id=entry_id))

    # GET: render form pre-filled
    tags_str = ", ".join(entry.get("tags", []))
    return render_template(
        "edit.html",
        entry=entry,
        tags_str=tags_str,
        categories=categories,
        subcategories=subcategories,
    )


@app.route("/entry/<int:entry_id>/delete", methods=["POST"])
def delete_entry(entry_id):
    entries = load_entries()
    new_entries = [e for e in entries if e.get("id") != entry_id]
    save_entries(new_entries)
    return redirect(url_for("index"))


@app.route("/dream/new", methods=["GET", "POST"])
def new_dream():
    entries = load_entries()

    if request.method == "POST":
        title = request.form["title"].strip()
        notes = request.form.get("notes", "").strip()
        dream_theme = request.form.get("dream_theme", "").strip()
        dream_priority = request.form.get("dream_priority", "").strip()
        dream_progress = request.form.get("dream_progress") or ""
        dream_target_date = request.form.get("dream_target_date", "").strip()

        entry_id = next_id(entries)

        entry = {
            "id": entry_id,
            "title": title,
            # You can choose a fixed date or let dreams also have a real date:
            "date": datetime.today().strftime("%Y-%m-%d"),
            "mood": "",
            "category": "Goals",
            "subcategory": "",
            "image_path": "",
            "notes": notes,
            "tags": ["dream"],
            "created_at": datetime.utcnow().isoformat(),
            "dream_theme": dream_theme,
            "dream_priority": dream_priority,
            "dream_progress": dream_progress,
            "dream_target_date": dream_target_date,
        }

        entries.append(entry)
        save_entries(entries)
        return redirect(url_for("dreamboard"))

    # For the dropdowns:
    themes = ["Career", "Travel", "Art", "Wellbeing", "Spiritual", "Growth"]
    priorities = ["High", "Medium", "Low"]

    return render_template("new_dream.html",
                           themes=themes,
                           priorities=priorities)


@app.route("/dreamboard")
def dreamboard():
    entries = load_entries()

    # 1) Decide which entries belong on the dreamboard
    dream_keywords = {"dream", "goal", "goals", "manifest", "manifestation"}

    dream_entries = []
    for e in entries:
        cat = (e.get("category") or "").lower()
        tags = [t.lower() for t in e.get("tags", [])]

        if cat in {"goal", "goals"} or dream_keywords.intersection(tags):
            dream_entries.append(e)

    # 2) Ensure dream fields exist (extra safety)
    for e in dream_entries:
        e.setdefault("dream_theme", e.get("category", ""))
        e.setdefault("dream_priority", "")
        e.setdefault("dream_target_date", "")
        e.setdefault("dream_progress", 0)

    # 3) Read filters from query params
    current_theme = request.args.get("theme") or None
    current_priority = request.args.get("priority") or None

    # 4) Build filter options
    themes = sorted({e.get("dream_theme") for e in dream_entries if e.get("dream_theme")})
    priorities = ["High", "Medium", "Low"]

    # 5) Apply filters
    if current_theme:
        dream_entries = [
            e for e in dream_entries
            if (e.get("dream_theme") or "").lower() == current_theme.lower()
        ]

    if current_priority:
        dream_entries = [
            e for e in dream_entries
            if (e.get("dream_priority") or "").lower() == current_priority.lower()
        ]

    # 6) Sort (by target date if present, then by regular date)
    def dream_sort_key(e):
        target = e.get("dream_target_date") or ""
        date = e.get("date") or ""
        return (target, date)

    dream_entries = sorted(dream_entries, key=dream_sort_key)

    # 7) Sidebar context (same pattern as other pages)
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "dreamboard.html",
        current_page="dreamboard",
        entries=dream_entries,
        themes=themes,
        priorities=priorities,
        current_theme=current_theme,
        current_priority=current_priority,
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
    )


@app.route("/milestones")
def milestones():
    entries = load_entries()

    def is_milestone(e):
        prog_raw = e.get("dream_progress") or 0
        try:
            prog = int(prog_raw)
        except (TypeError, ValueError):
            prog = 0

        tags = [t.lower() for t in e.get("tags", [])]
        return prog >= 80 or "milestone" in tags

    milestone_entries = [e for e in entries if is_milestone(e)]

    def sort_key(e):
        prog_raw = e.get("dream_progress") or 0
        try:
            prog = int(prog_raw)
        except (TypeError, ValueError):
            prog = 0
        target = e.get("dream_target_date") or ""
        return (-prog, target)

    milestone_entries = sorted(milestone_entries, key=sort_key)

    # sidebar data (same pattern as other pages)
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "milestones.html",
        current_page="milestones",
        entries=milestone_entries,
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=None,
        current_subcategory=None,
    )


@app.route("/stats")
def stats():
    entries = load_entries()

    total_entries = len(entries)

    # counts by collection & theme
    by_category = defaultdict(int)
    by_subcategory = defaultdict(int)
    by_mood = defaultdict(int)

    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        m = e.get("mood")
        if c:
            by_category[c] += 1
        if s:
            by_subcategory[s] += 1
        if m:
            by_mood[m] += 1

    # simple “this year” count
    current_year = datetime.today().strftime("%Y")
    this_year_entries = [
        e for e in entries
        if e.get("date") and e["date"].startswith(current_year)
    ]
    this_year_count = len(this_year_entries)

    # upcoming dream deadlines (next 60 days)
    today = datetime.today().date()
    upcoming = []
    for e in entries:
        dstr = e.get("dream_target_date") or ""
        if not dstr:
            continue
        try:
            d = datetime.strptime(dstr, "%Y-%m-%d").date()
        except ValueError:
            continue
        delta = (d - today).days
        if 0 <= delta <= 60:
            upcoming.append((delta, e))
    upcoming.sort(key=lambda x: x[0])
    upcoming_entries = [e for _, e in upcoming]

    # sidebar context
    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    # sort dicts for display
    top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)
    top_moods = sorted(by_mood.items(), key=lambda x: x[1], reverse=True)

    return render_template(
        "stats.html",
        current_page="stats",
        total_entries=total_entries,
        this_year_count=this_year_count,
        top_categories=top_categories,
        top_moods=top_moods,
        upcoming_entries=upcoming_entries,
        categories=categories,
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=None,
        current_subcategory=None,
    )


@app.route("/reflect", methods=["GET", "POST"])
def daily_reflection():
    entries = load_entries()

    if request.method == "POST":
        today_str = datetime.today().strftime("%Y-%m-%d")
        notes = request.form.get("notes", "").strip()
        mood = request.form.get("mood", "").strip()

        if notes:
            entry_id = next_id(entries)
            entry = {
                "id": entry_id,
                "title": f"Daily reflection – {today_str}",
                "date": today_str,
                "mood": mood,
                "category": "Life diary",
                "subcategory": "Daily reflection",
                "image_path": "",
                "notes": notes,
                "tags": ["reflection"],
                "created_at": datetime.utcnow().isoformat(),
                "dream_theme": "",
                "dream_priority": "",
                "dream_target_date": "",
                "dream_progress": 0,
            }
            entries.append(entry)
            save_entries(entries)
            return redirect(url_for("daily_reflection"))

    # GET: show recent reflections
    reflections = [
        e for e in entries
        if e.get("category") == "Life diary"
        and e.get("subcategory") == "Daily reflection"
    ]
    reflections = sorted(reflections, key=lambda e: e.get("date", ""), reverse=True)[:30]

    categories = sorted({e.get("category", "Art") for e in entries if e.get("category")})
    subcategories = sorted({e.get("subcategory", "") for e in entries if e.get("subcategory")})

    category_subcats = {}
    for e in entries:
        c = e.get("category")
        s = e.get("subcategory")
        if c and s:
            category_subcats.setdefault(c, []).append(s)

    # remove duplicates + sort
    category_subcats = {
        c: sorted(set(subs))
        for c, subs in category_subcats.items()
    }

    return render_template(
        "reflect.html",
        reflections=reflections,
        categories=categories,
        current_page="daily_reflection",
        subcategories=subcategories,
        category_subcats=category_subcats,
        current_category=None,
        current_subcategory=None,
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5050)
