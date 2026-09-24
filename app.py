import streamlit as st
import sqlite3
import json
import random
import pandas as pd
from datetime import datetime, timedelta
from groq import Groq

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="TestGen-Agent Pro",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MODERN UI STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .stButton>button { width: 100%; border-radius: 6px; font-weight: 600; }
    div.block-container { padding-top: 2rem; }
    </style>
""", unsafe_allow_html=True)

# --- LOCAL SQLITE DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect("exam_platform_poc.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS paper_configs 
                 (config_id TEXT PRIMARY KEY, category TEXT, board_stream TEXT, grade TEXT, subject TEXT, matrix_data TEXT, num_sets INTEGER, exam_time TEXT, generated INT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS paper_sets 
                 (set_id TEXT PRIMARY KEY, config_id TEXT, set_name TEXT, data TEXT, unlock_time TEXT, expires_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS submissions 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, student TEXT, set_id TEXT, score REAL, total_marks REAL, student_answers TEXT, agent_report TEXT, submitted_at TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    return sqlite3.connect("exam_platform_poc.db", check_same_thread=False)

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.title("TestGen-Agent")
    st.caption("Autonomous Academic Intelligence (Groq Powered)")
    st.markdown("---")
    api_key_input = st.text_input("🔑 Groq API Key", type="password", help="Enter your free Groq API key from console.groq.com")
    st.markdown("---")
    role = st.selectbox(
        "🧭 Navigation Portal", 
        ["Teacher Dashboard", "Student Examination Portal", "Analytics & Reports Hub", "Live Database Inspector"]
    )

# --- GROQ HELPER FUNCTION ---
def call_groq_llm(api_key, prompt):
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",  # <--- Use this verified free-tier Groq model ID
        messages=[
            {"role": "system", "content": "You are an elite academic assessment builder. Respond strictly with clean output."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

# --- JIT GENERATION HELPER ---
def run_jit_generation(config_id, api_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time FROM paper_configs WHERE config_id = ?", (config_id,))
    config_row = c.fetchone()
    
    if not config_row:
        conn.close()
        return False, "Config ID not found."
        
    cat, b_stream, grd, subj, matrix_json, n_sets, exam_time_str = config_row
    scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S")
    
    try:
        matrix_specs = json.loads(matrix_json)
        
        for i in range(n_sets):
            set_name = f"Set_{chr(65+i)}"
            set_id = f"{subj[:3].upper()}_{set_name}_{random.randint(1111,9999)}"
            
            prompt = f"""
            Create a rigorous academic question paper set ({set_name}) adhering strictly to:
            Category: {cat}, Stream/Board: {b_stream}, Grade: {grd}, Subject: {subj}.
            Based on this section matrix breakdown: {json.dumps(matrix_specs)}.
            Ensure unique wording to prevent cheating. Return ONLY a raw valid JSON array format and nothing else:
            [
              {{
                "id": "q1",
                "chapter": "Chapter Name",
                "type": "MCQ",
                "q": "Question string?",
                "options": ["A", "B", "C", "D"],
                "correct": "A",
                "marks": 2
              }}
            ]
            """
            raw_text = call_groq_llm(api_key, prompt)
            if raw_text.startswith("```json"): raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"): raw_text = raw_text[3:-3].strip()
            
            parsed_q = json.loads(raw_text)
            expire_dt = scheduled_dt + timedelta(hours=3)
            
            c.execute("INSERT OR REPLACE INTO paper_sets VALUES (?, ?, ?, ?, ?, ?)",
                      (set_id, config_id, set_name, json.dumps(parsed_q), exam_time_str, str(expire_dt)))
                      
        c.execute("UPDATE paper_configs SET generated = 1 WHERE config_id = ?", (config_id,))
        conn.commit()
        conn.close()
        return True, "Success"
    except Exception as e:
        conn.close()
        return False, str(e)

def fetch_config(config_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated FROM paper_configs WHERE config_id = ?", (config_id,))
    row = c.fetchone()
    conn.close()
    return row

# ==========================================
# 1. TEACHER PORTAL
# ==========================================
if role == "Teacher Dashboard":
    st.header("📋 Teacher Dashboard: Autonomous Curriculum & Blueprint Hub")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        category = st.selectbox("Institution Category", ["School Board (K-12)", "College / University Stream", "Competitive / Entrance Exam"])
    with col2:
        if category == "School Board (K-12)":
            board_stream = st.selectbox("Education Board", ["CBSE", "ICSE", "State Board (General)", "IB / IGCSE"])
        elif category == "College / University Stream":
            board_stream = st.selectbox("Stream", ["B.Tech / Computer Science", "B.Sc (Pure Sciences)", "B.Com / Management", "Medical / MBBS Basics"])
        else:
            board_stream = st.selectbox("Entrance Target", ["JEE (Main & Advanced)", "NEET (Medical)", "GATE (Engineering)", "UPSC Prelims"])
    with col3:
        if category == "School Board (K-12)":
            grade = st.selectbox("Class / Grade", ["Class 8", "Class 9", "Class 10", "Class 11", "Class 12"])
        elif category == "College / University Stream":
            grade = st.selectbox("Semester", ["Semester 1", "Semester 2", "Semester 3", "Semester 4", "Final Year"])
        else:
            grade = st.selectbox("Target Tier", ["Target Tier 1", "Target Tier 2"])

    st.markdown("### 📚 Subject Discovery & Mapping")
    sub_col1, sub_col2 = st.columns([3, 1])
    with sub_col1:
        if api_key_input and st.button("🤖 Discover Official Subjects via Groq"):
            with st.spinner("Querying board frameworks..."):
                try:
                    prompt = f"List official core subjects for Category: {category}, Board/Stream: {board_stream}, Level: {grade}. Return ONLY a raw JSON array of strings: [\"Subject 1\", \"Subject 2\"]."
                    clean_res = call_groq_llm(api_key_input, prompt)
                    if clean_res.startswith("```json"): clean_res = clean_res[7:-3].strip()
                    elif clean_res.startswith("```"): clean_res = clean_res[3:-3].strip()
                    st.session_state.fetched_subjects = json.loads(clean_res)
                    st.success("Subjects discovered!")
                except Exception as e:
                    st.error(f"Discovery error: {e}")

        if "fetched_subjects" in st.session_state and st.session_state.fetched_subjects:
            subject = st.selectbox("Select Discovered Subject", st.session_state.fetched_subjects)
        else:
            subject = st.text_input("Core Subject Name", "Mathematics")

    st.markdown("---")
    st.subheader("⚙️ Section Blueprint & Chapter Matrix")
    if api_key_input and st.button("✨ Auto-Populate Matrix"):
        with st.spinner("Extracting standard syllabus matrix..."):
            try:
                prompt = f"""
                Provide official chapters and key topic units for Board: {board_stream}, Grade: {grade}, Subject: {subject}.
                Return ONLY a raw JSON array of objects with keys 'chapter' and 'topics' (as a comma-separated string):
                [{{"chapter": "Chapter Name 1", "topics": "Topic A, Topic B"}}]
                """
                clean_res = call_groq_llm(api_key_input, prompt)
                if clean_res.startswith("```json"): clean_res = clean_res[7:-3].strip()
                elif clean_res.startswith("```"): clean_res = clean_res[3:-3].strip()
                discovered_matrix = json.loads(clean_res)
                
                st.session_state.matrix_rows = []
                for item in discovered_matrix:
                    st.session_state.matrix_rows.append({"chapter": item.get("chapter", ""), "topics": item.get("topics", ""), "q_type": "MCQ", "count": 2, "marks": 2})
                st.success("Syllabus mapped!")
                st.rerun()
            except Exception as e:
                st.error(f"Mapping failed: {e}")

    if "matrix_rows" not in st.session_state:
        st.session_state.matrix_rows = [{"chapter": "", "topics": "", "q_type": "MCQ", "count": 2, "marks": 2}]

    matrix_input_data = []
    for idx, row in enumerate(st.session_state.matrix_rows):
        cols = st.columns([2, 3, 2, 1, 1, 1])
        with cols[0]: ch = st.text_input(f"Chapter {idx+1}", value=row["chapter"], key=f"ch_{idx}")
        with cols[1]: tp = st.text_input(f"Topics {idx+1}", value=row["topics"], key=f"tp_{idx}")
        with cols[2]: qt = st.selectbox(f"Type {idx+1}", ["MCQ", "Short Answer", "Numerical / Derivation"], index=["MCQ", "Short Answer", "Numerical / Derivation"].index(row["q_type"]), key=f"qt_{idx}")
        with cols[3]: cnt = st.number_input(f"Count {idx+1}", min_value=1, value=row["count"], key=f"cnt_{idx}")
        with cols[4]: mks = st.number_input(f"Marks {idx+1}", min_value=1, value=row["marks"], key=f"mks_{idx}")
        with cols[5]:
            st.write("")
            st.write("")
            if st.button("🗑️", key=f"del_{idx}"):
                if len(st.session_state.matrix_rows) > 1:
                    st.session_state.matrix_rows.pop(idx)
                    st.rerun()
        matrix_input_data.append({"chapter": ch, "topics": tp, "q_type": qt, "count": cnt, "marks": mks})

    if st.button("➕ Add Section Row"):
        st.session_state.matrix_rows.append({"chapter": "", "topics": "", "q_type": "MCQ", "count": 2, "marks": 2})
        st.rerun()

    st.markdown("---")
    col_s1, col_s2 = st.columns(2)
    with col_s1: num_sets = st.slider("Parallel Anti-Cheating Randomized Sets", 1, 4, 3)
    with col_s2:
        exam_date = st.date_input("Exam Date")
        exam_time = st.time_input("Exam Start Time")
        
    scheduled_dt_str = f"{exam_date} {exam_time}"
    
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        if st.button("🚀 Schedule Exam Blueprint", type="primary"):
            if not api_key_input: st.error("Groq API Key required.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = get_db_connection()
                c = conn.cursor()
                # Fixed 8-column explicit insert to prevent operational errors
                c.execute(
                    "INSERT OR REPLACE INTO paper_configs (config_id, category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (config_id, category, board_stream, grade, subject, json.dumps(matrix_input_data), num_sets, scheduled_dt_str)
                )
                conn.commit()
                conn.close()
                st.success(f"✅ Config scheduled! Copy this Config ID for students: **{config_id}**")
    with b_col2:
        if st.button("⚡ Force Generate & Lock Sets Now"):
            if not api_key_input: st.error("Groq API Key required.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT OR REPLACE INTO paper_configs (config_id, category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (config_id, category, board_stream, grade, subject, json.dumps(matrix_input_data), num_sets, scheduled_dt_str)
                )
                conn.commit()
                conn.close()
                with st.spinner("Synthesizing multi-set question banks with Groq..."):
                    success, msg = run_jit_generation(config_id, api_key_input)
                    if success: st.success(f"🔥 Successfully generated! Copy this Config ID: **{config_id}**")
                    else: st.error(f"Generation error: {msg}")

# ==========================================
# 2. STUDENT PORTAL
# ==========================================
elif role == "Student Examination Portal":
    st.header("📝 Student Assessment Portal")
    col_login1, col_login2 = st.columns(2)
    with col_login1: student_name = st.text_input("Full Name", "Alex Morgan")
    with col_login2: input_config_id = st.text_input("Assessment Config ID")
        
    if input_config_id:
        config_row = fetch_config(input_config_id)
        if config_row:
            cat, b_stream, grd, subj, matrix_json, n_sets, exam_time_str, is_generated = config_row
            scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S")
            jit_trigger_dt = scheduled_dt - timedelta(minutes=2)
            current_time = datetime.now()
            
            if current_time >= jit_trigger_dt and is_generated == 0:
                if api_key_input:
                    run_jit_generation(input_config_id, api_key_input)
                    config_row = fetch_config(input_config_id)
                    is_generated = config_row[7]

            if current_time < jit_trigger_dt:
                st.warning(f"⏳ Assessment is locked until **{exam_time_str}**.")
            elif is_generated == 0:
                st.error("⚠️ Assessment configuration awaiting activation key sync.")
            else:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT set_id, set_name, data, unlock_time, expires_at FROM paper_sets WHERE config_id = ?", (input_config_id,))
                available_sets = c.fetchall()
                conn.close()
                
                if available_sets:
                    chosen_set = st.selectbox("Select Assigned Set Variant", available_sets, format_func=lambda x: f"{x[1]} (ID: {x[0]})")
                    set_id, set_name, data_json, u_time, e_time = chosen_set
                    
                    if datetime.now() > datetime.strptime(e_time, "%Y-%m-%d %H:%M:%S"):
                        st.error("❌ Submission window has expired.")
                    else:
                        st.success(f"Session Active — **{set_name}** loaded successfully.")
                        questions = json.loads(data_json)
                        
                        with st.form("student_live_exam"):
                            student_answers = {}
                            for idx, q in enumerate(questions):
                                st.markdown(f"**Q{idx+1}. [{q.get('chapter','General')}] {q['q']}** *({q['marks']} Marks)*")
                                if "options" in q and q["options"]:
                                    opts = q["options"].copy()
                                    student_answers[q['id']] = st.radio(f"Select choice {idx+1}", opts, key=f"ans_{set_id}_{q['id']}")
                                else:
                                    student_answers[q['id']] = st.text_input(f"Answer {idx+1}", key=f"ans_{set_id}_{q['id']}")
                                    
                            submitted_exam = st.form_submit_button("📤 Submit Final Examination", type="primary")
                            if submitted_exam:
                                if not api_key_input: st.error("Groq API Key required.")
                                else:
                                    with st.spinner("Evaluating submissions..."):
                                        score = 0
                                        total_marks = 0
                                        for q in questions:
                                            total_marks += q['marks']
                                            if str(student_answers.get(q['id'])).strip().lower() == str(q['correct']).strip().lower():
                                                score += q['marks']
                                                
                                        try:
                                            eval_prompt = f"Analyze this student exam submission: Student: {student_name}, Score: {score}/{total_marks}. Provide a detailed diagnostic report in clear markdown."
                                            agent_report = call_groq_llm(api_key_input, eval_prompt)
                                        except Exception:
                                            agent_report = "Deterministic evaluation report compiled successfully."
                                            
                                        conn = get_db_connection()
                                        c = conn.cursor()
                                        c.execute("INSERT INTO submissions (student, set_id, score, total_marks, student_answers, agent_report, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                                  (student_name, set_id, score, total_marks, json.dumps(student_answers), agent_report, str(datetime.now())))
                                        conn.commit()
                                        conn.close()
                                        
                                        st.balloons()
                                        st.success(f"🎉 Exam Submitted! Final Score: **{score} / {total_marks}**")
                                        st.markdown("---")
                                        st.markdown(agent_report)
        else: st.error("Invalid Configuration ID.")

# ==========================================
# 3. ANALYTICS & REPORTS HUB
# ==========================================
elif role == "Analytics & Reports Hub":
    st.header("📊 Analytics & Performance Hub")
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, student, set_id, score, total_marks, agent_report, submitted_at FROM submissions ORDER BY id DESC")
    subs = c.fetchall()
    conn.close()
    
    if not subs: st.info("No submission records found yet.")
    else:
        for sub in subs:
            sub_id, s_name, s_set, score, t_marks, report, s_time = sub
            pct = (score / t_marks * 100) if t_marks > 0 else 0
            with st.expander(f"👤 {s_name} | Set: {s_set} | Score: {score}/{t_marks} ({pct:.1f}%) | {s_time}"):
                st.progress(pct / 100.0)
                st.markdown(report)

# ==========================================
# 4. LIVE DATABASE INSPECTOR (For Live Demos)
# ==========================================
elif role == "Live Database Inspector":
    st.header("🔍 Live Database Inspector (SQLite POC)")
    st.write("Inspect the raw underlying relational database tables directly inside the app interface for live presentation.")
    
    table_choice = st.selectbox("Select Database Table to Inspect", ["paper_configs", "paper_sets", "submissions"])
    
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_choice}", conn)
        st.metric(f"Total Rows in `{table_choice}`", len(df))
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.info(f"Table `{table_choice}` is currently empty. Run an action in the Teacher or Student portal first!")
    finally:
        conn.close()
