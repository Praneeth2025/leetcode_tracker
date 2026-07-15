"""
LeetCode Practice Tracker
-------------------------
A Streamlit app to log topics + problems you've solved/not solved,
and generate practice sets:
  - "Mix Practice": 1 solved + 2 unsolved problems, picked from ANY topic
  - "Topic Practice": 1 solved + 2 unsolved problems, picked from ONE chosen topic

Data persists locally in a JSON file (leetcode_data.json) in the same
folder as this script, so your data survives across app restarts.

Run with:
    pip install streamlit
    streamlit run leetcode_tracker.py
"""

import json
import os
import random
from datetime import datetime

import streamlit as st

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leetcode_data.json")

# --------------------------------------------------------------------------
# Persistence helpers
# --------------------------------------------------------------------------

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def init_state():
    if "data" not in st.session_state:
        st.session_state.data = load_data()
    if "mix_result" not in st.session_state:
        st.session_state.mix_result = None
    if "topic_result" not in st.session_state:
        st.session_state.topic_result = None


def ensure_topic(topic):
    if topic not in st.session_state.data:
        st.session_state.data[topic] = {"solved": [], "unsolved": []}


def add_problems(topic, solved_raw, unsolved_raw):
    topic = topic.strip()
    if not topic:
        st.warning("Please enter a topic name.")
        return

    ensure_topic(topic)

    def parse_list(raw):
        # split on newlines or commas, strip blanks
        items = []
        for line in raw.replace(",", "\n").split("\n"):
            line = line.strip()
            if line:
                items.append(line)
        return items

    solved_items = parse_list(solved_raw)
    unsolved_items = parse_list(unsolved_raw)

    added_solved, added_unsolved = 0, 0

    for item in solved_items:
        if item not in st.session_state.data[topic]["solved"]:
            st.session_state.data[topic]["solved"].append(item)
            added_solved += 1
        # if it was previously unsolved, move it to solved
        if item in st.session_state.data[topic]["unsolved"]:
            st.session_state.data[topic]["unsolved"].remove(item)

    for item in unsolved_items:
        if item not in st.session_state.data[topic]["unsolved"] and item not in st.session_state.data[topic]["solved"]:
            st.session_state.data[topic]["unsolved"].append(item)
            added_unsolved += 1

    save_data(st.session_state.data)
    st.success(f"Added to '{topic}': {added_solved} solved, {added_unsolved} unsolved problem(s).")


def delete_problem(topic, bucket, problem):
    st.session_state.data[topic][bucket].remove(problem)
    # clean up empty topic
    if not st.session_state.data[topic]["solved"] and not st.session_state.data[topic]["unsolved"]:
        del st.session_state.data[topic]
    save_data(st.session_state.data)


# --------------------------------------------------------------------------
# Practice-set generators
# --------------------------------------------------------------------------

def all_solved_pool():
    pool = []
    for topic, buckets in st.session_state.data.items():
        for prob in buckets["solved"]:
            pool.append((topic, prob))
    return pool


def all_unsolved_pool():
    pool = []
    for topic, buckets in st.session_state.data.items():
        for prob in buckets["unsolved"]:
            pool.append((topic, prob))
    return pool


def generate_mix_set():
    solved_pool = all_solved_pool()
    unsolved_pool = all_unsolved_pool()

    if len(solved_pool) < 1 or len(unsolved_pool) < 2:
        return None, (len(solved_pool), len(unsolved_pool))

    chosen_solved = random.sample(solved_pool, 1)
    chosen_unsolved = random.sample(unsolved_pool, 2)

    result = [
        {"type": "Solved (revise)", "topic": t, "problem": p} for t, p in chosen_solved
    ] + [
        {"type": "Unsolved (new)", "topic": t, "problem": p} for t, p in chosen_unsolved
    ]
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

    result = [
        {"type": "Solved (revise)", "topic": topic, "problem": p} for p in chosen_solved
    ] + [
        {"type": "Unsolved (new)", "topic": topic, "problem": p} for p in chosen_unsolved
    ]
    random.shuffle(result)
    return result, None


def render_result_cards(result):
    for item in result:
        badge = "🟢 SOLVED" if "Solved" in item["type"] else "🔴 NEW"
        st.markdown(
            f"""
            <div style="border:1px solid #444;border-radius:10px;padding:12px 16px;margin-bottom:10px;">
                <span style="font-size:0.8em;opacity:0.7;">{badge} &nbsp;|&nbsp; Topic: <b>{item['topic']}</b></span>
                <div style="font-size:1.1em;margin-top:4px;">{item['problem']}</div>
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
st.caption("Log topics and problems, then generate practice sets (1 solved + 2 unsolved).")

tab_add, tab_mix, tab_topic, tab_manage = st.tabs(
    ["➕ Add Problems", "🎲 Mix Practice (Any Topic)", "🎯 Topic Practice", "📋 Manage / View Data"]
)

# ---- Tab 1: Add problems ----
with tab_add:
    st.subheader("Log a topic's problems")
    topic_input = st.text_input("Topic (e.g. Arrays, DP, Graphs, Sliding Window)")

    col1, col2 = st.columns(2)
    with col1:
        solved_input = st.text_area(
            "Problems you SOLVED",
            placeholder="One per line or comma-separated\ne.g.\nTwo Sum\nBest Time to Buy and Sell Stock",
            height=180,
        )
    with col2:
        unsolved_input = st.text_area(
            "Problems you DIDN'T solve",
            placeholder="One per line or comma-separated\ne.g.\n3Sum\nContainer With Most Water",
            height=180,
        )

    if st.button("Save Problems", type="primary"):
        add_problems(topic_input, solved_input, unsolved_input)

# ---- Tab 2: Mix practice (any topic) ----
with tab_mix:
    st.subheader("Generate a 3-question set from ANY topic")
    st.write("Picks **1 solved** problem (for revision) + **2 unsolved** problems (new challenge), from your full pool.")

    if st.button("🎲 Give me 3 questions", type="primary"):
        result, shortage = generate_mix_set()
        if result is None:
            s, u = shortage
            st.error(
                f"Not enough problems yet. You have {s} solved and {u} unsolved "
                f"across all topics — need at least 1 solved and 2 unsolved."
            )
            st.session_state.mix_result = None
        else:
            st.session_state.mix_result = result

    if st.session_state.mix_result:
        render_result_cards(st.session_state.mix_result)

# ---- Tab 3: Topic-specific practice ----
with tab_topic:
    st.subheader("Generate a 3-question set for ONE topic")
    topics = sorted(st.session_state.data.keys())

    if not topics:
        st.info("No topics logged yet. Add some in the 'Add Problems' tab first.")
    else:
        chosen_topic = st.selectbox("Choose a topic", topics)

        if st.button("🎯 Give me 3 questions from this topic", type="primary"):
            result, shortage = generate_topic_set(chosen_topic)
            if result is None:
                s, u = shortage
                st.error(
                    f"'{chosen_topic}' only has {s} solved and {u} unsolved problems — "
                    f"need at least 1 solved and 2 unsolved."
                )
                st.session_state.topic_result = None
            else:
                st.session_state.topic_result = result

        if st.session_state.topic_result:
            render_result_cards(st.session_state.topic_result)

# ---- Tab 4: Manage / view ----
with tab_manage:
    st.subheader("Your logged data")
    if not st.session_state.data:
        st.info("Nothing logged yet.")
    else:
        for topic in sorted(st.session_state.data.keys()):
            buckets = st.session_state.data[topic]
            with st.expander(f"📁 {topic}  —  {len(buckets['solved'])} solved / {len(buckets['unsolved'])} unsolved"):
                st.markdown("**✅ Solved**")
                if buckets["solved"]:
                    for prob in list(buckets["solved"]):
                        c1, c2 = st.columns([5, 1])
                        c1.write(f"- {prob}")
                        if c2.button("🗑️", key=f"del_solved_{topic}_{prob}"):
                            delete_problem(topic, "solved", prob)
                            st.rerun()
                else:
                    st.caption("None yet.")

                st.markdown("**❌ Unsolved**")
                if buckets["unsolved"]:
                    for prob in list(buckets["unsolved"]):
                        c1, c2 = st.columns([5, 1])
                        c1.write(f"- {prob}")
                        if c2.button("🗑️", key=f"del_unsolved_{topic}_{prob}"):
                            delete_problem(topic, "unsolved", prob)
                            st.rerun()
                else:
                    st.caption("None yet.")

    st.divider()
    st.caption(f"Data file: `{DATA_FILE}`")
    st.caption(f"Last loaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")