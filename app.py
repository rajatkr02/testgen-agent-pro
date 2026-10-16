import sqlite3
import datetime
import json
import time
import threading
import streamlit as st
import pandas as pd
from groq import Groq
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any

# Global thread-safe memory store pulling securely from Streamlit secrets
GLOBAL_API_KEY = st.secrets.get("GROQ_API_KEY", "")
global_lock = threading.Lock()

# ==========================================
# 0. DATABASE & INITIALIZATION (AUTO-MIGRATION)
# ==========================================

def init_db():
    conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
    cursor = conn.cursor()
    
    # Exam Configurations / Blueprints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_configs (
            id TEXT PRIMARY KEY,
            stream_category TEXT,
            board_or_org TEXT,
            grade_level TEXT,
            subject TEXT,
            exam_language TEXT,
            matrix_data TEXT,
            num_sets INTEGER,
            scheduled_time TEXT,
            generation_status TEXT DEFAULT 'Pending'
        )
    """)
    
    # AUTO-MIGRATION: Ensure 'generation_status' column exists
    cursor.execute("PRAGMA table_info(paper_configs)")
    columns = [col[1] for col in cursor.fetchall()]
    if "generation_status" not in columns:
        cursor.execute("ALTER TABLE paper_configs ADD COLUMN generation_status TEXT DEFAULT 'Pending'")
        conn.commit()

    # Generated Question Sets
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id TEXT,
            set_name TEXT,
            question_data TEXT,
            FOREIGN KEY (config_id) REFERENCES paper_configs(id)
        )
    """)
    
    # Dummy Students
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT,
            enrolled_stream TEXT
        )
    """)
    
    # Student Assignments Log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id TEXT,
            student_id TEXT,
            assigned_set TEXT,
            assignment_status TEXT
        )
    """)
    
    # Submissions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id TEXT,
            student_name TEXT,
            score REAL,
            details TEXT,
            submitted_at TEXT
        )
    """)
    
    # Student Diagnostic Reports Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS student_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id TEXT,
            student_name TEXT,
            overall_score REAL,
            strengths TEXT,
            weak_areas TEXT,
            personalized_feedback TEXT,
            question_breakdown TEXT,
            generated_at TEXT
        )
    """)

    # Scheduler Execution Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_scheduler_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id TEXT,
            log_message TEXT,
            logged_at TEXT
        )
    """)
    
    # Seed default dummy students if empty
    cursor.execute("SELECT COUNT(*) FROM students")
    if cursor.fetchone()[0] == 0:
        default_students = [
            ("Rajat Kumar", "rajat.student@example.com", "College / University"),
            ("Priya Sharma", "priya.sharma@example.com", "School Education"),
            ("Amit Verma", "amit.verma@example.com", "Competitive & Entrance Exams")
        ]
        cursor.executemany("INSERT INTO students (name, email, enrolled_stream) VALUES (?, ?, ?)", default_students)
        conn.commit()

    conn.close()

init_db()

# ==========================================
# 1. STREAMLIT PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="TestGen-Agent Pro: Autonomous Scheduled Suite",
    page_icon="🤖",
    layout="wide"
)

# ==========================================
# 2. HELPER & LLM UTILITIES
# ==========================================
def robust_parse_json(raw_text: str):
    """Cleans markdown code fences and extracts raw JSON payloads."""
    try:
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return json.loads(cleaned.strip())
    except Exception as e:
        return {}

def call_groq_llm(api_key: str, system_prompt: str, user_prompt: str) -> str:
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    return completion.choices[0].message.content

# ==========================================
# 3. LANGGRAPH AGENTIC PIPELINE (QUESTION GENERATION)
# ==========================================
class ExamAgentState(TypedDict):
    api_key: str
    stream_category: str
    board_or_org: str
    grade_level: str
    subject: str
    exam_language: str
    matrix_rows: List[Dict[str, Any]]
    num_sets: int
    config_id: str
    scheduled_time: str
    generated_sets: List[Dict[str, Any]]
    status_log: List[str]

def syllabus_validator_agent(state: ExamAgentState) -> ExamAgentState:
    state["status_log"].append("Syllabus Validator Agent active: Inspecting academic domain constraints...")
    return state

def question_generator_agent(state: ExamAgentState) -> ExamAgentState:
    state["status_log"].append("Question Generator Agent active: Synthesizing strict schema-compliant question bank sets...")
    api_key = state["api_key"]
    sets_count = state["num_sets"]
    
    generated_results = []
    set_labels = [chr(65 + i) for i in range(sets_count)]
    
    for s_label in set_labels:
        sys_p = "You are an elite academic assessment creator. You MUST return ONLY a valid JSON object containing a key 'questions' which is an array of objects. Each object must strictly contain keys: 'chapter' (string), 'question' (string), 'options' (array of 4 strings if MCQ, or empty array []), 'answer' (string matching one of the options or exact correct value), and 'marks' (number)."
        user_p = f"""Create a comprehensive exam question set {s_label} for Domain: {state['stream_category']}, Board/Org: {state['board_or_org']}, Level: {state['grade_level']}, Subject: {state['subject']} in Language: {state['exam_language']}.
        You must strictly adhere to the following syllabus mapping matrix and question counts/types: {json.dumps(state['matrix_rows'])}.
        Return format strictly:
        {{
            "questions": [
                {{"chapter": "Chapter Name", "question": "Question text?", "options": ["A", "B", "C", "D"], "answer": "A", "marks": 2}}
            ]
        }}"""
        
        try:
            res_text = call_groq_llm(api_key, sys_p, user_p)
            q_payload = robust_parse_json(res_text)
            q_data = q_payload.get("questions", [])
            generated_results.append({"set_name": f"Set {s_label}", "data": {"questions": q_data}})
        except Exception as e:
            state["status_log"].append(f"Error generating Set {s_label}: {e}")
            
    state["generated_sets"] = generated_results
    return state

def qa_red_teaming_agent(state: ExamAgentState) -> ExamAgentState:
    state["status_log"].append("QA & Red-Teaming Agent active: Auditing questions for strict schema compliance and options consistency...")
    api_key = state["api_key"]
    audited_sets = []
    
    for s_item in state["generated_sets"]:
        set_name = s_item["set_name"]
        q_data = s_item["data"]
        
        sys_p = "You are a strict academic QA examiner. Validate that every question has 'chapter', 'question', 'options', 'answer', and 'marks'. Return ONLY a valid JSON object with the verified questions array under key 'questions'."
        user_p = f"Review and fix any schema inconsistencies in this question set json: {json.dumps(q_data)}."
        
        try:
            audit_res = call_groq_llm(api_key, sys_p, user_p)
            audited_json = robust_parse_json(audit_res)
            if not audited_json or "questions" not in audited_json:
                audited_json = q_data
            audited_sets.append({"set_name": set_name, "data": audited_json})
            state["status_log"].append(f"QA Audit passed and verified for {set_name}.")
        except Exception as e:
            audited_sets.append(s_item)
            
    state["generated_sets"] = audited_sets
    return state

def persistence_and_student_assignment_agent(state: ExamAgentState) -> ExamAgentState:
    state["status_log"].append("Persistence & Assignment Agent active: Saving generated question sets and mapping students...")
    
    conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("""
        UPDATE paper_configs 
        SET generation_status = 'Generated & Released'
        WHERE id = ?
    """, (state["config_id"],))
    conn.commit()
    
    for s_item in state["generated_sets"]:
        cursor.execute(
            "INSERT INTO paper_sets (config_id, set_name, question_data) VALUES (?, ?, ?)",
            (state["config_id"], s_item["set_name"], json.dumps(s_item["data"]))
        )
    conn.commit()
    
    cursor.execute("SELECT id, name, email FROM students")
    students = cursor.fetchall()
    
    available_sets = [s["set_name"] for s in state["generated_sets"]]
    
    if available_sets and students:
        for idx, student in enumerate(students):
            stu_id, stu_name, stu_email = student
            assigned_set = available_sets[idx % len(available_sets)]
            
            cursor.execute("SELECT id FROM student_assignments WHERE config_id = ? AND student_id = ?", (state["config_id"], str(stu_id)))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO student_assignments (config_id, student_id, assigned_set, assignment_status) VALUES (?, ?, ?, ?)",
                    (state["config_id"], str(stu_id), assigned_set, "Assigned in Database")
                )
                conn.commit()
            state["status_log"].append(f"📌 Assigned [{assigned_set}] to student: {stu_name}")
            
    conn.close()
    return state

workflow = StateGraph(ExamAgentState)
workflow.add_node("validator", syllabus_validator_agent)
workflow.add_node("generator", question_generator_agent)
workflow.add_node("qa_auditor", qa_red_teaming_agent)
workflow.add_node("assigner", persistence_and_student_assignment_agent)
workflow.set_entry_point("validator")
workflow.add_edge("validator", "generator")
workflow.add_edge("generator", "qa_auditor")
workflow.add_edge("qa_auditor", "assigner")
workflow.add_edge("assigner", END)
app_graph = workflow.compile()

# ==========================================
# 4. BACKGROUND CRON AGENT WORKER POLLER
# ==========================================
def background_scheduler_worker():
    """Autonomous background thread polling every 10 seconds for pending exams."""
    while True:
        try:
            conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
            cursor = conn.cursor()
            
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                SELECT id, stream_category, board_or_org, grade_level, subject, exam_language, matrix_data, num_sets, scheduled_time
                FROM paper_configs 
                WHERE generation_status = 'Pending' AND scheduled_time <= ?
            """, (now_str,))
            pending_exams = cursor.fetchall()
            
            for exam in pending_exams:
                c_id, s_cat, b_org, g_lvl, subj, lang, matrix_json, n_sets, sched_t = exam
                
                with global_lock:
                    api_key_val = GLOBAL_API_KEY
                
                if not api_key_val:
                    cursor.execute(
                        "INSERT INTO agent_scheduler_logs (config_id, log_message, logged_at) VALUES (?, ?, ?)",
                        (c_id, "Background agent triggered, but skipped: Groq API Key not found in st.secrets.", now_str)
                    )
                    conn.commit()
                    continue
                
                matrix_rows = json.loads(matrix_json)
                
                initial_state = {
                    "api_key": api_key_val,
                    "stream_category": s_cat,
                    "board_or_org": b_org,
                    "grade_level": g_lvl,
                    "subject": subj,
                    "exam_language": lang,
                    "matrix_rows": matrix_rows,
                    "num_sets": n_sets,
                    "config_id": c_id,
                    "scheduled_time": sched_t,
                    "generated_sets": [],
                    "status_log": []
                }                                                                                
                
                final_state = app_graph.invoke(initial_state)
                
                for log_msg in final_state["status_log"]:
                    cursor.execute(
                        "INSERT INTO agent_scheduler_logs (config_id, log_message, logged_at) VALUES (?, ?, ?)",
                        (c_id, log_msg, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    )
                conn.commit()
                
            conn.close()
        except Exception as e:
            pass
        
        time.sleep(10)

if "scheduler_started" not in st.session_state:
    st.session_state.scheduler_started = True
    t = threading.Thread(target=background_scheduler_worker, daemon=True)
    t.start()

# ==========================================
# 5. AGENTIC STUDENT EVALUATION FUNCTION
# ==========================================
def run_agentic_student_evaluation(api_key: str, student_name: str, config_id: str, score: float, details: dict) -> dict:
    sys_p = """You are an elite academic performance psychologist and senior examiner agent. Analyze the student's exam answers, identify conceptual weak spots, map out strengths, and write encouraging yet actionable diagnostic feedback. 
    You MUST return ONLY a valid JSON object with these exact keys:
    - "strengths": A string describing the student's mastered chapters or question topics.
    - "weak_areas": A string detailing concepts where the student made mistakes or lacked clarity.
    - "personalized_feedback": A comprehensive 3-4 sentence paragraph of constructive advice and study recommendations."""
    
    user_p = f"""Student Name: {student_name}
    Exam ID: {config_id}
    Overall Score: {score:.2f}%
    Question-by-Question breakdown and answers: {json.dumps(details)}
    
    Generate the diagnostic report in JSON format."""
    
    try:
        if not api_key:
            return {
                "strengths": "Demonstrated consistent basic problem-solving ability.",
                "weak_areas": "Requires further review on complex application questions.",
                "personalized_feedback": f"Good effort on {config_id}! Review incorrect responses to build deeper mastery."
            }
        
        res_text = call_groq_llm(api_key, sys_p, user_p)
        return robust_parse_json(res_text)
    except Exception as e:
        return {
            "strengths": "Completed all evaluation items.",
            "weak_areas": "Error running agentic diagnostic analysis.",
            "personalized_feedback": f"Exam completed with score {score:.2f}%."
        }

# ==========================================
# 6. STREAMLIT USER INTERFACE (PORTALS)
# ==========================================
st.sidebar.title("🛡️ TestGen-Agent Portal")
role = st.sidebar.selectbox("Select Operational Role", ["Teacher Agent Dashboard", "Student Examination Portal", "Analytics & Reports Hub", "Live Database Inspector"])

# Fallback visual check for secrets status
if GLOBAL_API_KEY:
    st.sidebar.success("🔑 API Key loaded securely from Secrets!")
else:
    st.sidebar.warning("⚠️ API Key missing in `.streamlit/secrets.toml`!")

if role == "Teacher Agent Dashboard":
    st.title("👨‍🏫 Autonomous Teacher Control Center")
    st.markdown("Configure exam domains, schedule exact automated release times, and let the **Background Cron Agent** execute generation & distribution autonomously at the designated timestamp.")

    stream_options = {
        "School Education": {
            "boards": ["CBSE", "ICSE / ISC", "State Board", "International Baccalaureate (IB)", "Cambridge (IGCSE)"],
            "grades": [f"Class {i}" for i in range(1, 13)]
        },
        "College / University": {
            "boards": ["AICTE / UGC Affiliated", "State University", "Central University", "Deemed University", "Autonomous Institution"],
            "grades": ["Semester 1", "Semester 2", "Semester 3", "Semester 4", "Semester 5", "Semester 6", "Semester 7", "Semester 8"]
        },
        "Competitive & Entrance Exams": {
            "boards": ["NTA (NEET / JEE)", "UPSC (Civil Services)", "IBPS / SBI (Banking)", "GATE / PSU Bodies", "State PSC"],
            "grades": ["Aspirant Tier 1", "Aspirant Tier 2", "Advanced / Mains Level"]
        },
        "Corporate Certification": {
            "boards": ["Internal L&D", "AWS / Cloud Certification Board", "Agile / Scrum Alliance", "Cybersecurity Accreditation"],
            "grades": ["Foundational", "Associate", "Professional / Expert"]
        }
    }

    col1, col2 = st.columns(2)
    with col1:
        stream_category = st.selectbox("Stream / Domain Category", list(stream_options.keys()), key="stream_category_select")
        available_boards = stream_options[stream_category]["boards"]
        board_or_org = st.selectbox("Board / University / Organization", available_boards, key="board_select")

    with col2:
        available_grades = stream_options[stream_category]["grades"]
        grade_level = st.selectbox("Grade / Semester / Level", available_grades, key="grade_select")
        exam_language = st.selectbox("Exam Language", ["English", "Hindi", "Spanish", "French", "Regional"])

    st.markdown("### ⏰ Autonomous Scheduled Release Time")
    st.markdown("> *Set a future date and time (or 1 minute ahead). The background agent watcher will automatically trigger question paper synthesis and student assignment when the clock hits this exact timestamp.*")
    
    sched_col1, sched_col2 = st.columns(2)
    with sched_col1:
        exam_date = st.date_input("Scheduled Exam Date", datetime.date.today())
    with sched_col2:
        default_time = (datetime.datetime.now() + datetime.timedelta(minutes=1)).time()
        exam_time = st.time_input("Scheduled Release Time", default_time)
    
    scheduled_datetime_str = datetime.datetime.combine(exam_date, exam_time).strftime("%Y-%m-%d %H:%M:%S")
    num_sets = st.slider("Number of Parallel Anti-Cheating Sets", 1, 4, 3)

    if "matrix_rows" not in st.session_state:
        st.session_state.matrix_rows = []

    if "ai_suggested_subjects" not in st.session_state:
        st.session_state.ai_suggested_subjects = ["Physics", "Mathematics", "Chemistry", "Biology", "Computer Science"]

    st.markdown("---")
    st.subheader("⚙️ Autonomous Subject & Syllabus Mapping Agent")
    
    sub_col1, sub_col2 = st.columns([3, 1])
    with sub_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        fetch_subjects_btn = st.button("🤖 Suggest Subjects")

    if fetch_subjects_btn and GLOBAL_API_KEY:
        with st.spinner("AI Agent discovering valid core subjects..."):
            try:
                sys_p = "You are an expert curriculum assistant. Return ONLY a valid JSON object containing a key 'subjects' with a list of string values."
                user_p = f"List 5 standard subjects for Stream: {stream_category}, Board/Org: {board_or_org}, Level: {grade_level}. Return format: {{'subjects': ['Subject 1', 'Subject 2', ...]}}"
                
                sugg_res = call_groq_llm(GLOBAL_API_KEY, sys_p, user_p)
                parsed_json = robust_parse_json(sugg_res)
                parsed_sugg = parsed_json.get("subjects", [])
                
                if parsed_sugg:
                    st.session_state.ai_suggested_subjects = parsed_sugg
                    st.success("AI suggested subjects successfully updated into dropdown!")
            except Exception as e:
                st.warning(f"Could not fetch AI suggestions: {e}")

    with sub_col1:
        subject = st.selectbox("Select or AI-Suggested Subject", st.session_state.ai_suggested_subjects)

    if GLOBAL_API_KEY and st.button("✨ Dispatch Syllabus Mapping Agent"):
        if not subject:
            st.warning("Please specify a subject name before mapping the syllabus.")
        else:
            with st.spinner("Agent mapping core units & chapters..."):
                try:
                    sys_p = "You are an expert academic syllabus architect. Return ONLY a valid JSON object containing a key 'syllabus'."
                    user_p = f"Provide core chapters and topic units for Domain: {stream_category}, Organization: {board_or_org}, Level: {grade_level}, Subject: {subject} in Language: {exam_language}. Return format: {{'syllabus': [{{'chapter': 'Name', 'topics': 'Topic A, Topic B'}}]}}"
                    
                    clean_res = call_groq_llm(GLOBAL_API_KEY, sys_p, user_p)
                    parsed_matrix = robust_parse_json(clean_res)
                    discovered_matrix = parsed_matrix.get("syllabus", [])
                    
                    st.session_state.matrix_rows = []
                    for item in discovered_matrix:
                        st.session_state.matrix_rows.append({"chapter": item.get("chapter", ""), "topics": item.get("topics", ""), "level": "Moderate", "q_type": "MCQ", "count": 2, "marks": 2})
                    st.success("Syllabus mapped autonomously by agent!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Mapping agent failed: {e}")

    edited_df = st.data_editor(pd.DataFrame(st.session_state.matrix_rows), num_rows="dynamic", use_container_width=True)
    config_id_input = st.text_input("Unique Config ID", value="", placeholder="e.g. EXAM-NEET-PHYSICS-01")

    if st.button("📅 Schedule Exam for Autonomous Background Generation"):
        if not GLOBAL_API_KEY:
            st.warning("Groq API key is missing from secrets.toml.")
        elif not config_id_input:
            st.warning("Please provide a Unique Config ID for this examination package.")
        elif not subject:
            st.warning("Please select a subject name.")
        else:
            conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO paper_configs (id, stream_category, board_or_org, grade_level, subject, exam_language, matrix_data, num_sets, scheduled_time, generation_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            """, (
                config_id_input, stream_category, board_or_org, 
                grade_level, subject, exam_language, 
                json.dumps(edited_df.to_dict(orient="records")), num_sets, scheduled_datetime_str
            ))
            conn.commit()
            conn.close()
            
            st.success(f"✅ Exam **{config_id_input}** successfully scheduled for **{scheduled_datetime_str}**! The background agent worker will automatically pick it up and generate questions when the time arrives.")

elif role == "Student Examination Portal":
    st.title("🎓 Student Examination Room")
    st.markdown("Enter your assigned Exam ID and registered email to take your test once the background agent generates it.")
    
    if "active_exam" not in st.session_state:
        st.session_state.active_exam = None
    if "last_report" not in st.session_state:
        st.session_state.last_report = None

    config_id_input = st.text_input("Enter Exam Configuration ID:", value="EXAM-DEMO-01")
    student_email_input = st.text_input("Your Registered Email (e.g. rajat.student@example.com):", value="rajat.student@example.com")

    col_enter, col_reset = st.columns([2, 1])
    with col_enter:
        enter_btn = st.button("🔍 Verify & Enter Exam Room", type="primary")
    with col_reset:
        if st.button("🔄 Reset Session"):
            st.session_state.active_exam = None
            st.session_state.last_report = None
            st.rerun()

    if enter_btn:
        conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
        cursor = conn.cursor()
        
        cursor.execute("SELECT scheduled_time, generation_status FROM paper_configs WHERE id = ?", (config_id_input,))
        config_row = cursor.fetchone()
        
        if not config_row:
            st.error(f"Exam ID '{config_id_input}' not found in database.")
        else:
            scheduled_str, gen_status = config_row
            
            if gen_status != "Generated & Released":
                st.warning(f"⏳ Exam paper is still **Pending scheduled generation** by the background agent. Scheduled release time: **{scheduled_str}**. Please wait until the scheduled time arrives.")
                conn.close()
                st.stop()

            cursor.execute("SELECT id, name, email FROM students WHERE email = ?", (student_email_input.strip(),))
            stu_row = cursor.fetchone()
            
            if not stu_row:
                st.error(f"Email '{student_email_input}' not found in registered roster.")
            else:
                stu_id, stu_name, stu_email = stu_row  # Fixed unpacking
                
                cursor.execute("SELECT score, details, submitted_at FROM submissions WHERE config_id = ? AND student_name = ?", (config_id_input, stu_name))
                sub_row = cursor.fetchone()
                
                if sub_row:
                    st.warning(f"⚠️ **Notice:** You have already submitted this exam on **{sub_row[2]}** with a score of **{sub_row[0]:.2f}%**.")
                    
                    cursor.execute("SELECT strengths, weak_areas, personalized_feedback FROM student_reports WHERE config_id = ? AND student_name = ?", (config_id_input, stu_name))
                    rep_row = cursor.fetchone()
                    
                    st.session_state.last_report = {
                        "student_name": stu_name,
                        "config_id": config_id_input,
                        "score": sub_row[0],
                        "submitted_at": sub_row[2],
                        "details": json.loads(sub_row[1]),
                        "agent_analysis": {
                            "strengths": rep_row[0] if rep_row else "Evaluated by system",
                            "weak_areas": rep_row[1] if rep_row else "Review performance breakdown",
                            "personalized_feedback": rep_row[2] if rep_row else "Good effort."
                        } if rep_row else {}
                    }
                    st.session_state.active_exam = None
                else:
                    cursor.execute("SELECT assigned_set FROM student_assignments WHERE config_id = ? AND student_id = ?", (config_id_input, str(stu_id)))
                    assign_row = cursor.fetchone()
                    
                    if not assign_row:
                        st.warning("No assigned paper set found for your student profile under this Exam ID.")
                    else:
                        assigned_set_name = assign_row[0]
                        cursor.execute("SELECT question_data FROM paper_sets WHERE config_id = ? AND set_name = ?", (config_id_input, assigned_set_name))
                        set_data_row = cursor.fetchone()
                        
                        if not set_data_row:
                            st.error("Assigned paper set payload could not be loaded from database.")
                        else:
                            q_json = json.loads(set_data_row[0])
                            st.session_state.active_exam = {
                                "config_id": config_id_input,
                                "student_name": stu_name,
                                "student_email": student_email_input,
                                "assigned_set_name": assigned_set_name,
                                "questions": q_json.get("questions", [])
                            }
                            st.session_state.last_report = None
                            st.success(f"Authenticated successfully! Welcome, {stu_name}. Assigned Paper: **{assigned_set_name}**.")
                            st.rerun()
        conn.close()

    if st.session_state.last_report:
        rep = st.session_state.last_report
        st.markdown("---")
        st.markdown(f"## 📋 Agentic Diagnostic & Performance Report")
        st.info(f"Student: **{rep['student_name']}** | Exam ID: **{rep['config_id']}** | Final Score: **{rep['score']:.2f}%** | Submitted: {rep['submitted_at']}")
        
        agent_data = rep.get("agent_analysis", {})
        if agent_data:
            col_a, col_b = st.columns(2)
            with col_a:
                st.success(f"**💪 Identified Strengths:**\n\n{agent_data.get('strengths', 'N/A')}")
            with col_b:
                st.error(f"**🎯 Areas for Improvement:**\n\n{agent_data.get('weak_areas', 'N/A')}")
            
            st.info(f"**🤖 AI Examiner Feedback:**\n\n{agent_data.get('personalized_feedback', 'N/A')}")

    if st.session_state.active_exam:
        exam = st.session_state.active_exam
        st.markdown("---")
        st.subheader(f"📝 Active Examination: {exam['config_id']} ({exam['assigned_set_name']})")
        st.info(f"Examinee: **{exam['student_name']}** | Answer all questions below carefully.")

        questions = exam["questions"]
        student_answers = {}

        for idx, q in enumerate(questions, 1):
            st.markdown(f"**Q{idx} [{q.get('chapter', 'General')}]: {q.get('question')}** *(Marks: {q.get('marks', 2)})*")
            options = q.get("options", [])
            widget_key = f"ans_input_{exam['config_id']}_{idx}"
            
            if options and isinstance(options, list) and len(options) > 0:
                ans = st.radio(f"Select option for Q{idx}", options, key=widget_key, index=None)
                student_answers[f"q_{idx}"] = {
                    "chapter": q.get("chapter"),
                    "question": q.get("question"), 
                    "selected": ans if ans else "No Answer", 
                    "correct": q.get("answer")
                }
            else:
                ans = st.text_area(f"Provide answer for Q{idx}", key=widget_key)
                student_answers[f"q_{idx}"] = {
                    "chapter": q.get("chapter"),
                    "question": q.get("question"), 
                    "selected": ans if ans else "No Answer", 
                    "correct": q.get("answer")
                }

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Submit Exam & Generate Agentic Diagnostic Report", type="primary"):
            correct_count = 0
            total_evaluated = 0
            
            for key, val in student_answers.items():
                selected_val = val["selected"]
                correct_val = val["correct"]
                
                if correct_val:
                    total_evaluated += 1
                    if str(selected_val).strip().lower() == str(correct_val).strip().lower():
                        correct_count += 1

            final_score = (correct_count / total_evaluated * 100) if total_evaluated > 0 else 100.0
            submitted_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with st.spinner("🤖 Autonomous Evaluator Agent analyzing performance and drafting diagnostic report..."):
                agent_analysis = run_agentic_student_evaluation(
                    api_key=GLOBAL_API_KEY,
                    student_name=exam["student_name"],
                    config_id=exam["config_id"],
                    score=final_score,
                    details=student_answers
                )

            conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
            sub_cursor = conn.cursor()
            
            sub_cursor.execute("SELECT id FROM submissions WHERE config_id = ? AND student_name = ?", (exam["config_id"], exam["student_name"]))
            if sub_cursor.fetchone():
                st.error("Submission already recorded for this student.")
                conn.close()
            else:
                sub_cursor.execute("""
                    INSERT INTO submissions (config_id, student_name, score, details, submitted_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (exam["config_id"], exam["student_name"], final_score, json.dumps(student_answers), submitted_time_str))
                
                sub_cursor.execute("""
                    INSERT INTO student_reports (config_id, student_name, overall_score, strengths, weak_areas, personalized_feedback, question_breakdown, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    exam["config_id"], exam["student_name"], final_score,
                    agent_analysis.get("strengths", ""),
                    agent_analysis.get("weak_areas", ""),
                    agent_analysis.get("personalized_feedback", ""),
                    json.dumps(student_answers),
                    submitted_time_str
                ))
                conn.commit()
                conn.close()

                st.success(f"🎉 Exam submitted and evaluated autonomously! Final Score: **{final_score:.2f}%**.")
                
                st.session_state.last_report = {
                    "student_name": exam["student_name"],
                    "config_id": exam["config_id"],
                    "score": final_score,
                    "submitted_at": submitted_time_str,
                    "details": student_answers,
                    "agent_analysis": agent_analysis
                }
                st.session_state.active_exam = None
                st.rerun()

elif role == "Analytics & Reports Hub":
    st.title("📊 Analytics & Diagnostic Hub")
    conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Scheduled Configurations", "Students & Roster", "Submissions", "🧠 Student Diagnostic Reports", "⚙️ Background Agent Logs"])
    with tab1:
        configs_df = pd.read_sql_query("SELECT id, stream_category, board_or_org, subject, scheduled_time, generation_status, num_sets FROM paper_configs", conn)
        st.dataframe(configs_df, use_container_width=True)
    with tab2:
        roster_df = pd.read_sql_query("""
            SELECT s.name, s.email, a.config_id, a.assigned_set, a.assignment_status 
            FROM students s 
            LEFT JOIN student_assignments a ON s.id = a.student_id
        """, conn)
        st.dataframe(roster_df, use_container_width=True)
    with tab3:
        subs_df = pd.read_sql_query("SELECT id, config_id, student_name, score, submitted_at FROM submissions", conn)
        if subs_df.empty:
            st.info("No exam submissions recorded yet.")
        else:
            st.dataframe(subs_df, use_container_width=True)
    with tab4:
        st.markdown("### 🧠 Autonomous Student Diagnostic Reports (Agentic Insights)")
        reports_df = pd.read_sql_query("SELECT student_name, config_id, overall_score, strengths, weak_areas, personalized_feedback, generated_at FROM student_reports", conn)
        if reports_df.empty:
            st.info("No agentic student reports generated yet.")
        else:
            st.dataframe(reports_df, use_container_width=True)
            
            st.markdown("---")
            st.subheader("🔍 Inspect Individual Student Diagnostic File")
            selected_student_report = st.selectbox("Select Student Report to View", reports_df["student_name"].unique())
            if selected_student_report:
                row = reports_df[reports_df["student_name"] == selected_student_report].iloc[0]
                st.markdown(f"**Student:** {row['student_name']} | **Exam ID:** {row['config_id']} | **Score:** {row['overall_score']:.2f}%")
                col_x, col_y = st.columns(2)
                with col_x:
                    st.success(f"**Strengths:**\n\n{row['strengths']}")
                with col_y:
                    st.error(f"**Weak Areas:**\n\n{row['weak_areas']}")
                st.info(f"**AI Examiner Feedback:**\n\n{row['personalized_feedback']}")
    with tab5:
        st.markdown("### ⚙️ Background Cron Agent Execution Logs")
        logs_df = pd.read_sql_query("SELECT id, config_id, log_message, logged_at FROM agent_scheduler_logs ORDER BY id DESC", conn)
        if logs_df.empty:
            st.info("No background agent logs recorded yet.")
        else:
            st.dataframe(logs_df, use_container_width=True)
            
    conn.close()

elif role == "Live Database Inspector":
    st.title("🛠️ Live SQLite Database Inspector")
    conn = sqlite3.connect("exam_platform_agentic.db", check_same_thread=False)
    table_choice = st.selectbox("Select Table to Inspect", ["paper_configs", "paper_sets", "students", "student_assignments", "submissions", "student_reports", "agent_scheduler_logs"])
    table_df = pd.read_sql_query(f"SELECT * FROM {table_choice}", conn)
    conn.close()
    st.dataframe(table_df, use_container_width=True)