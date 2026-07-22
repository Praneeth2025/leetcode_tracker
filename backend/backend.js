/**
 * LeetCode Practice Tracker — backend API (MongoDB Atlas edition)
 * -----------------------------------------------------------------
 * Same REST contract as the JSON-file version, but persists everything to
 * MongoDB Atlas instead of local files. Database name: "leetcode_solver".
 *
 * Collections:
 *   - problems : one document per (topic, name) pair.
 *       { topic, name, difficulty, status: "solved" | "unsolved" }
 *     This is the source of truth for the Add Problems / Mix Practice /
 *     Topic Practice / Manage tabs — the {topic: {solved:[], unsolved:[]}}
 *     shape the frontend expects is assembled from these documents on read.
 *   - schedules : a single document (fixed _id: "current") holding the
 *       active N-day schedule, in the same shape the old
 *       leetcode_schedule.json used ({ created_at, num_days, days }).
 *
 * Setup:
 *   1. Put your Atlas connection string in a .env file next to this script:
 *        MONGODB_URI="mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority"
 *      (Also accepts MONGO_URL / MONGO_URI as key names, in case that's
 *      what's already in your .env.)
 *   2. npm install
 *   3. node server.js        # listens on https://leetcode-tracker-patn.onrender.com
 */

require("dotenv").config();

console.log(process.env.MONGO_URI); 

const express = require("express");
const cors = require("cors");
const { MongoClient } = require("mongodb");

const MONGO_URI =
  process.env.MONGODB_URI || process.env.MONGO_URL || process.env.MONGO_URI;

if (!MONGO_URI) {
  console.error(
    "Missing Mongo connection string. Add MONGODB_URI (or MONGO_URL) to your .env file."
  );
  process.exit(1);
}

const DB_NAME = "leetcode_solver";
const DIFFICULTIES = ["Easy", "Medium", "Hard"];

const app = express();
app.use(cors());
app.use(express.json());

let problemsCol;
let schedulesCol;

async function connectDb() {
  const client = new MongoClient(MONGO_URI);
  await client.connect();
  console.log("Connected to MongoDB Atlas");
  const db = client.db(DB_NAME);
  problemsCol = db.collection("problems");
  schedulesCol = db.collection("schedules");
  await problemsCol.createIndex({ topic: 1, name: 1 }, { unique: true });
  console.log(`Connected to MongoDB Atlas — database "${DB_NAME}"`);
}

function shuffle(arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function sample(arr, n) {
  return shuffle(arr).slice(0, n);
}

// --------------------------------------------------------------------------
// problems collection helpers
// --------------------------------------------------------------------------

/** Reassembles the {topic: {solved:[], unsolved:[]}} shape from documents. */
async function loadData() {
  const docs = await problemsCol.find({}).toArray();
  const data = {};
  for (const doc of docs) {
    if (!data[doc.topic]) data[doc.topic] = { solved: [], unsolved: [] };
    data[doc.topic][doc.status].push({
      name: doc.name,
      difficulty: doc.difficulty || null,
    });
  }
  return data;
}

/** Upserts a single problem's solved/unsolved status. One doc per
 *  (topic, name) — setting the status here is what "moves" a problem
 *  between solved/unsolved, since there's only ever one doc for it. */
async function upsertResult(topic, name, difficulty, solved) {
  topic = topic || "General";
  const status = solved ? "solved" : "unsolved";

  const update = { $set: { topic, name, status } };
  if (difficulty) {
    update.$set.difficulty = difficulty;
  } else {
    update.$setOnInsert = { difficulty: null };
  }

  await problemsCol.updateOne({ topic, name }, update, { upsert: true });
}

// --------------------------------------------------------------------------
// Data routes
// --------------------------------------------------------------------------

app.get("/api/data", async (req, res) => {
  res.json({ data: await loadData() });
});

app.get("/api/topics", async (req, res) => {
  const topics = await problemsCol.distinct("topic");
  res.json({ topics: topics.sort() });
});

app.post("/api/data/manual", async (req, res) => {
  const { topic, solved = [], unsolved = [] } = req.body;
  const t = (topic || "").trim();
  if (!t) return res.status(400).json({ error: "Topic is required." });

  let addedSolved = 0;
  let addedUnsolved = 0;

  for (const name of solved) {
    await problemsCol.updateOne(
      { topic: t, name },
      { $set: { topic: t, name, status: "solved" }, $setOnInsert: { difficulty: null } },
      { upsert: true }
    );
    addedSolved++;
  }

  for (const name of unsolved) {
    const existing = await problemsCol.findOne({ topic: t, name });
    if (!existing) {
      await problemsCol.insertOne({ topic: t, name, status: "unsolved", difficulty: null });
      addedUnsolved++;
    }
  }

  res.json({ data: await loadData(), addedSolved, addedUnsolved });
});

app.delete("/api/data/:topic/:bucket/:name", async (req, res) => {
  const { topic, bucket, name } = req.params;
  if (!["solved", "unsolved"].includes(bucket)) {
    return res.status(400).json({ error: "Invalid bucket." });
  }
  await problemsCol.deleteOne({ topic, name: decodeURIComponent(name), status: bucket });
  res.json({ data: await loadData() });
});

// --------------------------------------------------------------------------
// Schedule routes
// --------------------------------------------------------------------------

async function loadSchedule() {
  const doc = await schedulesCol.findOne({ _id: "current" });
  if (!doc) return null;
  const { _id, ...schedule } = doc;
  return schedule;
}

async function saveSchedule(schedule) {
  await schedulesCol.replaceOne({ _id: "current" }, { _id: "current", ...schedule }, { upsert: true });
}

app.get("/api/schedule", async (req, res) => {
  res.json({ schedule: await loadSchedule() });
});

app.post("/api/schedule", async (req, res) => {
  const { problems, numDays, shuffle: shouldShuffle } = req.body;
  if (!Array.isArray(problems) || problems.length === 0) {
    return res.status(400).json({ error: "Please provide at least one problem." });
  }
  const n = Math.max(1, parseInt(numDays, 10) || 1);
  const ordered = shouldShuffle ? shuffle(problems) : problems.slice();

  const days = Array.from({ length: n }, () => []);
  ordered.forEach((p, i) => {
    const difficulty = DIFFICULTIES.includes(p.difficulty) ? p.difficulty : "Unspecified";
    days[i % n].push({
      name: p.name,
      difficulty,
      topic: p.topic || "General",
      status: "pending",
    });
  });

  const schedule = {
    created_at: new Date().toISOString().replace("T", " ").slice(0, 19),
    num_days: n,
    days,
  };
  await saveSchedule(schedule);
  res.json({ schedule });
});

app.post("/api/schedule/mark", async (req, res) => {
  const { dayIndex, itemIndex, solved } = req.body;
  const schedule = await loadSchedule();
  if (!schedule || !schedule.days[dayIndex] || !schedule.days[dayIndex][itemIndex]) {
    return res.status(404).json({ error: "Schedule item not found." });
  }
  const entry = schedule.days[dayIndex][itemIndex];
  entry.status = solved ? "solved" : "unsolved";
  await saveSchedule(schedule);
  await upsertResult(entry.topic, entry.name, entry.difficulty, solved);
  res.json({ schedule, data: await loadData() });
});

app.post("/api/schedule/reset", async (req, res) => {
  const { dayIndex, itemIndex } = req.body;
  const schedule = await loadSchedule();
  if (!schedule || !schedule.days[dayIndex] || !schedule.days[dayIndex][itemIndex]) {
    return res.status(404).json({ error: "Schedule item not found." });
  }
  schedule.days[dayIndex][itemIndex].status = "pending";
  await saveSchedule(schedule);
  res.json({ schedule });
});

app.delete("/api/schedule", async (req, res) => {
  await schedulesCol.deleteOne({ _id: "current" });
  res.json({ schedule: null });
});

// --------------------------------------------------------------------------
// Practice-set routes (Mix / Topic)
// --------------------------------------------------------------------------

app.get("/api/practice/mix", async (req, res) => {
  const solvedDocs = await problemsCol.find({ status: "solved" }).toArray();
  const unsolvedDocs = await problemsCol.find({ status: "unsolved" }).toArray();
  if (solvedDocs.length < 1 || unsolvedDocs.length < 2) {
    return res.status(400).json({
      error: "Not enough problems yet.",
      solvedCount: solvedDocs.length,
      unsolvedCount: unsolvedDocs.length,
    });
  }
  const chosenSolved = sample(solvedDocs, 1).map((d) => ({
    type: "Solved (revise)",
    topic: d.topic,
    problem: { name: d.name, difficulty: d.difficulty || null },
  }));
  const chosenUnsolved = sample(unsolvedDocs, 2).map((d) => ({
    type: "Unsolved (new)",
    topic: d.topic,
    problem: { name: d.name, difficulty: d.difficulty || null },
  }));
  res.json({ result: shuffle([...chosenSolved, ...chosenUnsolved]) });
});

app.get("/api/practice/topic/:topic", async (req, res) => {
  const topic = req.params.topic;
  const solvedDocs = await problemsCol.find({ topic, status: "solved" }).toArray();
  const unsolvedDocs = await problemsCol.find({ topic, status: "unsolved" }).toArray();
  if (solvedDocs.length < 1 || unsolvedDocs.length < 2) {
    return res.status(400).json({
      error: `'${topic}' doesn't have enough problems yet.`,
      solvedCount: solvedDocs.length,
      unsolvedCount: unsolvedDocs.length,
    });
  }
  const chosenSolved = sample(solvedDocs, 1).map((d) => ({
    type: "Solved (revise)",
    topic,
    problem: { name: d.name, difficulty: d.difficulty || null },
  }));
  const chosenUnsolved = sample(unsolvedDocs, 2).map((d) => ({
    type: "Unsolved (new)",
    topic,
    problem: { name: d.name, difficulty: d.difficulty || null },
  }));
  res.json({ result: shuffle([...chosenSolved, ...chosenUnsolved]) });
});

// --------------------------------------------------------------------------

const PORT = process.env.PORT || 5000;

connectDb()
  .then(() => {
    app.listen(PORT, () => {
      console.log(`LeetCode Tracker backend listening on http://localhost:${PORT}`);
    });
  })
  .catch((err) => {
    console.error("Failed to connect to MongoDB Atlas:", err.message);
    process.exit(1);
  });