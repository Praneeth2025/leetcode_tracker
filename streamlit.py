"""
LeetCode Practice Tracker
-------------------------
Features:
  1. Schedule Builder — paste a list of problems (with difficulty, optional topic),
     pick N days, and it shuffles + splits them into a day-by-day schedule.
     Mark each problem Solved / Not Solved right from the schedule — that result
     is stored automatically.
  2. Mix Practice — one button gives 3 questions from your WHOLE pool:
     1 solved (revise) + 2 unsolved (new), across all topics.
  3. Topic Practice — same idea, scoped to one topic.
  4. Manage / View — see and edit everything you've logged.

Data persists locally in two JSON files next to this script:
  leetcode_data.json      -> solved/unsolved problems by topic
  leetcode_schedule.json  -> your current N-day schedule

Run with:
    pip install streamlit
    streamlit run leetcode_tracker.py
"""

import json
import os
import random
from datetime import datetime

import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "leetcode_data.json")
SCHEDULE_FILE = os.path.join(BASE_DIR, "leetcode_schedule.json")

DIFFICULTY_COLORS = {
    "Easy": "#2ecc71",
    "Medium": "#f39c12",
    "Hard": "#e74c3c",
    None: "#888888",
}

# --------------------------------------------------------------------------
# Persistence helpers
# --------------------------------------------------------------------------

def _normalize_problem(item):
    """Support old string-only entries; upgrade to dict form."""
    if isinstance(item, str):
        return {"name": item, "difficulty": None}
    return {"name": item.get("name", ""), "difficulty": item.get("difficulty")}


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                raw = json.load(f)
            except json.JSONDecodeError:
                return {}
        for topic, buckets in raw.items():
            buckets["solved"] = [_normalize_problem(p) for p in buckets.get("solved", [])]
            buckets["unsolved"] = [_normalize_problem(p) for p in buckets.get("unsolved", [])]
        return raw
    return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_schedule():
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return None
    return None


def save_schedule(schedule):
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, indent=2)


def init_state():
    if "data" not in st.session_state:
        st.session_state.data = load_data()
    if "schedule" not in st.session_state:
        st.session_state.schedule = load_schedule()
    if "mix_result" not in st.session_state:
        st.session_state.mix_result = None
    if "topic_result" not in st.session_state:
        st.session_state.topic_result = None


def ensure_topic(topic):
    if topic not in st.session_state.data:
        st.session_state.data[topic] = {"solved": [], "unsolved": []}


# --------------------------------------------------------------------------
# Core data operations (topic -> solved/unsolved problem dicts)
# --------------------------------------------------------------------------

def upsert_result(topic, name, difficulty, solved):
    """Record that `name` was solved or not, under `topic`. Moves it out of
    the opposite bucket if it was there, and updates difficulty if given."""
    topic = topic or "General"
    ensure_topic(topic)
    target = "solved" if solved else "unsolved"
    other = "unsolved" if solved else "solved"

    st.session_state.data[topic][other] = [
        p for p in st.session_state.data[topic][other] if p["name"] != name
    ]

    existing = next((p for p in st.session_state.data[topic][target] if p["name"] == name), None)
    if existing:
        if difficulty:
            existing["difficulty"] = difficulty
    else:
        st.session_state.data[topic][target].append({"name": name, "difficulty": difficulty})

    save_data(st.session_state.data)


def add_problems_manual(topic, solved_raw, unsolved_raw):
    topic = topic.strip()
    if not topic:
        st.warning("Please enter a topic name.")
        return

    ensure_topic(topic)

    def parse_list(raw):
        items = []
        for line in raw.replace(",", "\n").split("\n"):
            line = line.strip()
            if line:
                items.append(line)
        return items

    solved_items = parse_list(solved_raw)
    unsolved_items = parse_list(unsolved_raw)

    added_solved, added_unsolved = 0, 0
    solved_names = {p["name"] for p in st.session_state.data[topic]["solved"]}
    unsolved_names = {p["name"] for p in st.session_state.data[topic]["unsolved"]}

    for item in solved_items:
        st.session_state.data[topic]["unsolved"] = [
            p for p in st.session_state.data[topic]["unsolved"] if p["name"] != item
        ]
        if item not in solved_names:
            st.session_state.data[topic]["solved"].append({"name": item, "difficulty": None})
            solved_names.add(item)
            added_solved += 1

    for item in unsolved_items:
        if item not in unsolved_names and item not in solved_names:
            st.session_state.data[topic]["unsolved"].append({"name": item, "difficulty": None})
            unsolved_names.add(item)
            added_unsolved += 1

    save_data(st.session_state.data)
    st.success(f"Added to '{topic}': {added_solved} solved, {added_unsolved} unsolved problem(s).")


def delete_problem(topic, bucket, name):
    st.session_state.data[topic][bucket] = [
        p for p in st.session_state.data[topic][bucket] if p["name"] != name
    ]
    if not st.session_state.data[topic]["solved"] and not st.session_state.data[topic]["unsolved"]:
        del st.session_state.data[topic]
    save_data(st.session_state.data)


# --------------------------------------------------------------------------
# Schedule builder
# --------------------------------------------------------------------------

def parse_schedule_input(raw):
    """Each line: Problem Name | Difficulty | Topic (topic optional).
    Falls back gracefully if only name + difficulty given."""
    problems = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        name = parts[0] if len(parts) > 0 else ""
        difficulty = parts[1].title() if len(parts) > 1 and parts[1] else "Unspecified"
        topic = parts[2] if len(parts) > 2 and parts[2] else "General"
        if difficulty not in ("Easy", "Medium", "Hard"):
            difficulty = "Unspecified"
        if name:
            problems.append({"name": name, "difficulty": difficulty, "topic": topic})
    return problems


def create_schedule(problems, num_days, shuffle=True):
    ordered = problems[:]
    if shuffle:
        random.shuffle(ordered)

    days = [[] for _ in range(num_days)]
    for i, prob in enumerate(ordered):
        entry = dict(prob)
        entry["status"] = "pending"  # pending | solved | unsolved
        days[i % num_days].append(entry)

    schedule = {
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "num_days": num_days,
        "days": days,
    }
    st.session_state.schedule = schedule
    save_schedule(schedule)


def mark_schedule_item(day_idx, item_idx, solved):
    entry = st.session_state.schedule["days"][day_idx][item_idx]
    entry["status"] = "solved" if solved else "unsolved"
    save_schedule(st.session_state.schedule)
    upsert_result(entry.get("topic", "General"), entry["name"], entry.get("difficulty"), solved)


def reset_schedule_item(day_idx, item_idx):
    st.session_state.schedule["days"][day_idx][item_idx]["status"] = "pending"
    save_schedule(st.session_state.schedule)


def difficulty_badge(difficulty):
    color = DIFFICULTY_COLORS.get(difficulty, "#888888")
    label = difficulty or "Unspecified"
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:6px;font-size:0.75em;">{label}</span>'


# --------------------------------------------------------------------------
# Practice-set generators (Mix / Topic)
# --------------------------------------------------------------------------

def all_solved_pool():
    return [(topic, p) for topic, b in st.session_state.data.items() for p in b["solved"]]


def all_unsolved_pool():
    return [(topic, p) for topic, b in st.session_state.data.items() for p in b["unsolved"]]


def generate_mix_set():
    solved_pool = all_solved_pool()
    unsolved_pool = all_unsolved_pool()
    if len(solved_pool) < 1 or len(unsolved_pool) < 2:
        return None, (len(solved_pool), len(unsolved_pool))
    chosen_solved = random.sample(solved_pool, 1)
    chosen_unsolved = random.sample(unsolved_pool, 2)
    result = (
        [{"type": "Solved (revise)", "topic": t, "problem": p} for t, p in chosen_solved]
        + [{"type": "Unsolved (new)", "topic": t, "problem": p} for t, p in chosen_unsolved]
    )
    random.shuffle(result)
    return result, None


def generate_topic_set(topic):
    buckets = st.session_state.data.get(topic, {"solved": [], "unsolved": []})
    solved_pool = buckets["solved"]
    unsolved_pool = buckets["unsolved"]
    if len(solved_pool) < 1 or len(unsolved_pool) < 2:
        return None, (len(solved_pool), len(unsolved_pool))
    chosen_solved = random.sample(solved_pool, 1)
    chosen_unsolved = random.sample(unsolved_pool, 2)
    result = (
        [{"type": "Solved (revise)", "topic": topic, "problem": p} for p in chosen_solved]
        + [{"type": "Unsolved (new)", "topic": topic, "problem": p} for p in chosen_unsolved]
    )
    random.shuffle(result)
    return result, None


def render_result_cards(result):
    for item in result:
        badge = "🟢 SOLVED" if "Solved" in item["type"] else "🔴 NEW"
        prob = item["problem"]
        st.markdown(
            f"""
            <div style="border:1px solid #444;border-radius:10px;padding:12px 16px;margin-bottom:10px;">
                <span style="font-size:0.8em;opacity:0.7;">{badge} &nbsp;|&nbsp; Topic: <b>{item['topic']}</b></span>
                <div style="font-size:1.1em;margin-top:4px;">{prob['name']} &nbsp;{difficulty_badge(prob.get('difficulty'))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

st.set_page_config(page_title="LeetCode Practice Tracker", page_icon="🧩", layout="centered")
init_state()

st.title("🧩 LeetCode Practice Tracker")

tab_schedule, tab_add, tab_mix, tab_topic, tab_manage = st.tabs(
    ["📅 Schedule", "➕ Add Problems", "🎲 Mix Practice", "🎯 Topic Practice", "📋 Manage / View"]
)

# ---- Tab: Schedule builder + tracker ----
with tab_schedule:
    st.subheader("Build your N-day schedule")
    st.caption("One problem per line, format: `Problem Name | Difficulty | Topic` (topic optional).")
    st.code("Two Sum | Easy | Arrays\n3Sum | Medium | Arrays\nMerge k Sorted Lists | Hard", language=None)

    raw_input = st.text_area("Paste your problem list", height=200, key="schedule_raw_input")
    num_days = st.number_input("Number of days", min_value=1, max_value=90, value=7, step=1)
    order_choice = st.radio(
        "Order",
        ["🔀 Shuffle randomly", "📌 Keep as entered"],
        horizontal=True,
    )
    should_shuffle = order_choice.startswith("🔀")

    button_label = "🔀 Shuffle & Create Schedule" if should_shuffle else "📌 Create Schedule (in order)"
    if st.button(button_label, type="primary"):
        problems = parse_schedule_input(raw_input)
        if not problems:
            st.warning("Please enter at least one problem.")
        else:
            create_schedule(problems, int(num_days), shuffle=should_shuffle)
            st.success(f"Created a {num_days}-day schedule with {len(problems)} problems.")
            st.rerun()

    st.divider()

    if not st.session_state.schedule:
        st.info("No schedule yet — create one above.")
    else:
        sched = st.session_state.schedule
        total = sum(len(d) for d in sched["days"])
        done = sum(1 for d in sched["days"] for e in d if e["status"] != "pending")
        st.caption(f"Schedule created {sched['created_at']} — {done}/{total} marked so far.")
        st.progress(done / total if total else 0)

        for day_idx, day_items in enumerate(sched["days"], start=1):
            day_done = sum(1 for e in day_items if e["status"] != "pending")
            with st.expander(f"Day {day_idx}  —  {day_done}/{len(day_items)} done", expanded=(day_done < len(day_items))):
                for item_idx, entry in enumerate(day_items):
                    c1, c2, c3 = st.columns([5, 1, 1])
                    with c1:
                        st.markdown(
                            f"**{entry['name']}** &nbsp; {difficulty_badge(entry.get('difficulty'))} "
                            f"&nbsp;<span style='opacity:0.6;font-size:0.8em;'>({entry.get('topic', 'General')})</span>",
                            unsafe_allow_html=True,
                        )
                        if entry["status"] == "solved":
                            st.caption("✅ Marked solved")
                        elif entry["status"] == "unsolved":
                            st.caption("❌ Marked not solved")
                    with c2:
                        if entry["status"] != "solved":
                            if st.button("✅", key=f"solve_{day_idx}_{item_idx}", help="Mark solved"):
                                mark_schedule_item(day_idx - 1, item_idx, True)
                                st.rerun()
                    with c3:
                        if entry["status"] != "unsolved":
                            if st.button("❌", key=f"unsolve_{day_idx}_{item_idx}", help="Mark not solved"):
                                mark_schedule_item(day_idx - 1, item_idx, False)
                                st.rerun()
                    if entry["status"] != "pending":
                        if st.button("↩️ reset", key=f"reset_{day_idx}_{item_idx}"):
                            reset_schedule_item(day_idx - 1, item_idx)
                            st.rerun()

        st.divider()
        if st.button("🗑️ Clear current schedule"):
            st.session_state.schedule = None
            if os.path.exists(SCHEDULE_FILE):
                os.remove(SCHEDULE_FILE)
            st.rerun()

# ---- Tab: Add problems manually (no schedule, just log directly) ----
with tab_add:
    st.subheader("Log problems directly to a topic")
    topic_input = st.text_input("Topic (e.g. Arrays, DP, Graphs, Sliding Window)")

    col1, col2 = st.columns(2)
    with col1:
        solved_input = st.text_area(
            "Problems you SOLVED", placeholder="One per line or comma-separated", height=180
        )
    with col2:
        unsolved_input = st.text_area(
            "Problems you DIDN'T solve", placeholder="One per line or comma-separated", height=180
        )

    if st.button("Save Problems", type="primary"):
        add_problems_manual(topic_input, solved_input, unsolved_input)

# ---- Tab: Mix practice ----
with tab_mix:
    st.subheader("3 questions from ANY topic")
    st.write("1 solved (revise) + 2 unsolved (new), pulled from your whole pool.")

    if st.button("🎲 Give me 3 questions", type="primary"):
        result, shortage = generate_mix_set()
        if result is None:
            s, u = shortage
            st.error(f"Not enough problems yet ({s} solved / {u} unsolved) — need at least 1 solved and 2 unsolved.")
            st.session_state.mix_result = None
        else:
            st.session_state.mix_result = result

    if st.session_state.mix_result:
        render_result_cards(st.session_state.mix_result)

# ---- Tab: Topic-specific practice ----
with tab_topic:
    st.subheader("3 questions from ONE topic")
    topics = sorted(st.session_state.data.keys())

    if not topics:
        st.info("No topics logged yet.")
    else:
        chosen_topic = st.selectbox("Choose a topic", topics)
        if st.button("🎯 Give me 3 questions from this topic", type="primary"):
            result, shortage = generate_topic_set(chosen_topic)
            if result is None:
                s, u = shortage
                st.error(f"'{chosen_topic}' only has {s} solved / {u} unsolved — need at least 1 solved and 2 unsolved.")
                st.session_state.topic_result = None
            else:
                st.session_state.topic_result = result

        if st.session_state.topic_result:
            render_result_cards(st.session_state.topic_result)

# ---- Tab: Manage / view ----
with tab_manage:
    st.subheader("Your logged data")
    if not st.session_state.data:
        st.info("Nothing logged yet.")
    else:
        for topic in sorted(st.session_state.data.keys()):
            buckets = st.session_state.data[topic]
            with st.expander(f"📁 {topic} — {len(buckets['solved'])} solved / {len(buckets['unsolved'])} unsolved"):
                st.markdown("**✅ Solved**")
                if buckets["solved"]:
                    for prob in list(buckets["solved"]):
                        c1, c2 = st.columns([5, 1])
                        c1.markdown(f"- {prob['name']} {difficulty_badge(prob.get('difficulty'))}", unsafe_allow_html=True)
                        if c2.button("🗑️", key=f"del_solved_{topic}_{prob['name']}"):
                            delete_problem(topic, "solved", prob["name"])
                            st.rerun()
                else:
                    st.caption("None yet.")

                st.markdown("**❌ Unsolved**")
                if buckets["unsolved"]:
                    for prob in list(buckets["unsolved"]):
                        c1, c2 = st.columns([5, 1])
                        c1.markdown(f"- {prob['name']} {difficulty_badge(prob.get('difficulty'))}", unsafe_allow_html=True)
                        if c2.button("🗑️", key=f"del_unsolved_{topic}_{prob['name']}"):
                            delete_problem(topic, "unsolved", prob["name"])
                            st.rerun()
                else:
                    st.caption("None yet.")

    st.divider()
    st.caption(f"Data file: `{DATA_FILE}`")
    st.caption(f"Schedule file: `{SCHEDULE_FILE}`")