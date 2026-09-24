import streamlit as st
import sqlite3
import json
import ast
import re
import random
import pandas as pd
from datetime import datetime, timedelta, timezone
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

# --- TIMEZONE SETUP (IST: UTC+5:30) ---
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    return datetime.now(IST)

# --- LOCAL SQLITE DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect("exam_platform_poc.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS paper_configs 
                 (config_id TEXT PRIMARY KEY, category TEXT, board_stream TEXT, grade TEXT, subject TEXT, language TEXT, matrix_data TEXT, num_sets INTEGER, exam_time TEXT, generated INT)''')
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
    st.caption("Autonomous Academic Intelligence")
    st.markdown("---")
    api_key_input = st.text_input("🔑 Groq API Key", type="password", help="Enter your free Groq API key from console.groq.com")
    st.markdown("---")
    exam_language = st.selectbox(
        "🌐 Language / Medium", 
        ["English", "Hindi (हिन्दी)", "Sanskrit (संस्कृतम्)", "Regional / Other"],
        index=0,
        help="Select output language for syllabus, questions, and evaluation reports."
    )
    st.markdown("---")
    role = st.selectbox(
        "🧭 Navigation Portal", 
        ["Teacher Dashboard", "Student Examination Portal", "Analytics & Reports Hub", "Live Database Inspector"]
    )

# --- GROQ HELPER FUNCTION ---
def call_groq_llm(api_key, prompt):
    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {"role": "system", "content": "You are an elite multi-lingual academic assessment builder. Respond strictly with raw valid JSON or structured Markdown as requested, preserving exact unicode/script characters (e.g., Devanagari for Hindi/Sanskrit)."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=4096
    )
    return response.choices[0].message.content.strip()

def robust_parse_json(raw_text):
    match = re.search(r'(\[.*\]|\{.*\})', raw_text, re.DOTALL)
    cleaned = match.group(0) if match else raw_text
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    
    try:
        return json.loads(cleaned)
    except Exception:
        try:
            fixed = cleaned.strip()
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')
            
            if open_braces < 0 or open_brackets < 0:
                fixed = fixed[:max(fixed.rfind('}'), fixed.rfind(']')) + 1]
                open_braces = fixed.count('{') - fixed.count('}')
                open_brackets = fixed.count('[') - fixed.count(']')
                
            fixed += '}' * max(0, open_braces)
            fixed += ']' * max(0, open_brackets)
            return json.loads(fixed)
        except Exception:
            try:
                return ast.literal_eval(cleaned)
            except Exception as e:
                raise ValueError(f"Failed to parse LLM response as JSON: {e}\nRaw response:\n{raw_text}")

# --- JIT GENERATION HELPER ---
def run_jit_generation(config_id, api_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, language, matrix_data, num_sets, exam_time FROM paper_configs WHERE config_id = ?", (config_id,))
    config_row = c.fetchone()
    
    if not config_row:
        conn.close()
        return False, "Config ID not found."
        
    cat, b_stream, grd, subj, lang, matrix_json, n_sets, exam_time_str = config_row
    
    try:
        scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
    except ValueError:
        scheduled_dt = get_ist_now()
    
    try:
        matrix_specs = json.loads(matrix_json)
        
        for i in range(n_sets):
            set_name = f"Set_{chr(65+i)}"
            set_id = f"{subj[:3].upper()}_{set_name}_{random.randint(1111,9999)}"
            
            prompt = f"""
            Create a rigorous academic question paper set ({set_name}) adhering strictly to:
            Category: {cat}, Stream/Board: {b_stream}, Grade: {grd}, Subject: {subj}.
            Language Medium: {lang} (Generate all questions, chapter names, options, and explanations in this exact language/script).
            Based on this section matrix breakdown (incorporating target difficulty levels like Easy/Moderate/High): {json.dumps(matrix_specs)}.
            Ensure unique wording to prevent cheating. Return ONLY a raw valid JSON array format and nothing else:
            [
              {{
                "id": "q1",
                "chapter": "Chapter Name in {lang}",
                "level": "Moderate",
                "type": "MCQ",
                "q": "Question string in {lang}?",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct": "Option A",
                "marks": 2
              }}
            ]
            """
            raw_text = call_groq_llm(api_key, prompt)
            parsed_q = robust_parse_json(raw_text)
            expire_dt = scheduled_dt + timedelta(hours=3)
            
            c.execute("INSERT OR REPLACE INTO paper_sets VALUES (?, ?, ?, ?, ?, ?)",
                      (set_id, config_id, set_name, json.dumps(parsed_q, ensure_ascii=False), str(scheduled_dt.strftime("%Y-%m-%d %H:%M:%S")), str(expire_dt.strftime("%Y-%m-%d %H:%M:%S"))))
                      
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
    c.execute("SELECT category, board_stream, grade, subject, language, matrix_data, num_sets, exam_time, generated FROM paper_configs WHERE config_id = ?", (config_id,))
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
        category = st.selectbox("Institution Category", ["School Board (K-12)", "College / University Stream", "Competitive / Entrance Exam"], key="teacher_category")
    with col2:
        if category == "School Board (K-12)":
            board_stream = st.selectbox("Education Board", ["CBSE", "ICSE", "State Board (General)", "IB / IGCSE"], key="board_k12")
        elif category == "College / University Stream":
            board_stream = st.selectbox("Stream", ["B.Tech / Computer Science", "B.Sc (Pure Sciences)", "B.Com / Management", "Medical / MBBS Basics"], key="board_uni")
        else:
            board_stream = st.selectbox("Entrance Target", ["JEE (Main & Advanced)", "NEET (Medical)", "GATE (Engineering)", "UPSC Prelims"], key="board_entrance")
    with col3:
        if category == "School Board (K-12)":
            grade = st.selectbox("Class / Grade", ["Class 8", "Class 9", "Class 10", "Class 11", "Class 12"], key="grade_k12")
        elif category == "College / University Stream":
            grade = st.selectbox("Semester", ["Semester 1", "Semester 2", "Semester 3", "Semester 4", "Final Year"], key="grade_uni")
        else:
            grade = st.selectbox("Target Tier", ["Target Tier 1", "Target Tier 2"], key="grade_entrance")

    st.markdown(f"### 📚 Subject Discovery & Mapping ({exam_language} Medium)")
    sub_col1, sub_col2 = st.columns([3, 1])
    with sub_col1:
        if api_key_input and st.button("🤖 Discover Official Subjects via Groq"):
            with st.spinner("Querying board frameworks..."):
                try:
                    prompt = f"List official core subjects for Category: {category}, Board/Stream: {board_stream}, Level: {grade}, Language/Medium: {exam_language}. Return ONLY a raw JSON array of strings in {exam_language}: [\"Subject 1\", \"Subject 2\"]."
                    clean_res = call_groq_llm(api_key_input, prompt)
                    st.session_state.fetched_subjects = robust_parse_json(clean_res)
                    st.success("Subjects discovered!")
                except Exception as e:
                    st.error(f"Discovery error: {e}")

        if "fetched_subjects" in st.session_state and st.session_state.fetched_subjects:
            subject = st.selectbox("Select Discovered Subject", st.session_state.fetched_subjects, key="selected_discovered_subject")
        else:
            default_subj = "हिन्दी (Hindi)" if "Hindi" in exam_language else ("संस्कृत (Sanskrit)" if "Sanskrit" in exam_language else "Mathematics")
            subject = st.text_input("Core Subject Name", default_subj, key="manual_subject_input")

    st.markdown("---")
    st.subheader("⚙️ Section Blueprint & Chapter Matrix")
    if api_key_input and st.button("✨ Auto-Populate Matrix"):
        with st.spinner("Extracting standard syllabus matrix..."):
            try:
                prompt = f"""
                Provide official core chapters and key topic units for Board: {board_stream}, Grade: {grade}, Subject: {subject} in Language: {exam_language}.
                Return ONLY a raw JSON array of objects with keys 'chapter' and 'topics' (as a comma-separated string) in {exam_language}:
                [{{"chapter": "Chapter Name", "topics": "Topic A, Topic B"}}]
                """
                clean_res = call_groq_llm(api_key_input, prompt)
                discovered_matrix = robust_parse_json(clean_res)
                
                st.session_state.matrix_rows = []
                for item in discovered_matrix:
                    st.session_state.matrix_rows.append({"chapter": item.get("chapter", ""), "topics": item.get("topics", ""), "level": "Moderate", "q_type": "MCQ", "count": 2, "marks": 2})
                st.success("Syllabus successfully mapped!")
                st.rerun()
            except Exception as e:
                st.error(f"Mapping failed: {e}")

    if "matrix_rows" not in st.session_state:
        default_ch = "काव्य खंड एवं गद्य खंड" if ("Hindi" in exam_language or "Sanskrit" in exam_language) else "Introduction & Fundamentals"
        st.session_state.matrix_rows = [{"chapter": default_ch, "topics": "Basic Concepts, Core Principles", "level": "Moderate", "q_type": "MCQ", "count": 2, "marks": 2}]

    matrix_input_data = []
    for idx, row in enumerate(st.session_state.matrix_rows):
        cols = st.columns([2, 3, 2, 1, 1, 1, 1])
        with cols[0]: ch = st.text_input(f"Chapter {idx+1}", value=row["chapter"], key=f"ch_{idx}")
        with cols[1]: tp = st.text_input(f"Topics {idx+1}", value=row["topics"], key=f"tp_{idx}")
        with cols[2]: lvl = st.selectbox(f"Level {idx+1}", ["Easy", "Moderate", "High"], index=["Easy", "Moderate", "High"].index(row.get("level", "Moderate")), key=f"lvl_{idx}")
        with cols[3]: qt = st.selectbox(f"Type {idx+1}", ["MCQ", "Short Answer", "Numerical / Derivation"], index=["MCQ", "Short Answer", "Numerical / Derivation"].index(row["q_type"]), key=f"qt_{idx}")
        with cols[4]: cnt = st.number_input(f"Count {idx+1}", min_value=1, value=row["count"], key=f"cnt_{idx}")
        with cols[5]: mks = st.number_input(f"Marks {idx+1}", min_value=1, value=row["marks"], key=f"mks_{idx}")
        with cols[6]:
            st.write("")
            st.write("")
            if st.button("🗑️", key=f"del_{idx}"):
                if len(st.session_state.matrix_rows) > 1:
                    st.session_state.matrix_rows.pop(idx)
                    st.rerun()
        matrix_input_data.append({"chapter": ch, "topics": tp, "level": lvl, "q_type": qt, "count": cnt, "marks": mks})

    if st.button("➕ Add Section Row"):
        st.session_state.matrix_rows.append({"chapter": "", "topics": "", "level": "Moderate", "q_type": "MCQ", "count": 2, "marks": 2})
        st.rerun()

    st.markdown("---")
    col_s1, col_s2 = st.columns(2)
    with col_s1: num_sets = st.slider("Parallel Anti-Cheating Randomized Sets", 1, 4, 3)
    with col_s2:
        current_ist = get_ist_now()
        exam_date = st.date_input("Exam Date", value=current_ist.date())
        exam_time = st.time_input("Exam Start Time", value=current_ist.time())
        
    scheduled_dt_str = f"{exam_date} {exam_time}"
    
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        if st.button("🚀 Schedule Exam Blueprint", type="primary"):
            if not api_key_input: st.error("Groq API Key required.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = get_db_connection()
                c = conn.cursor()
                c.execute(
                    "INSERT OR REPLACE INTO paper_configs (config_id, category, board_stream, grade, subject, language, matrix_data, num_sets, exam_time, generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (config_id, category, board_stream, grade, subject, exam_language, json.dumps(matrix_input_data, ensure_ascii=False), num_sets, scheduled_dt_str)
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
                    "INSERT OR REPLACE INTO paper_configs (config_id, category, board_stream, grade, subject, language, matrix_data, num_sets, exam_time, generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                    (config_id, category, board_stream, grade, subject, exam_language, json.dumps(matrix_input_data, ensure_ascii=False), num_sets, scheduled_dt_str)
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
    with col_login1: student_name = st.text_input("Full Name", value="")
    with col_login2: input_config_id = st.text_input("Assessment Config ID")
        
    if input_config_id and student_name.strip():
        config_row = fetch_config(input_config_id)
        if config_row:
            cat, b_stream, grd, subj, lang, matrix_json, n_sets, exam_time_str, is_generated = config_row
            
            try:
                scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            except ValueError:
                scheduled_dt = get_ist_now()
                
            current_dt = get_ist_now()
            
            if is_generated == 0 and current_dt >= (scheduled_dt - timedelta(minutes=2)):
                if api_key_input:
                    with st.spinner("⏰ Exam scheduled time reached or approaching! Automatically generating question sets..."):
                        success, msg = run_jit_generation(input_config_id, api_key_input)
                        if success:
                            st.success("✨ Sets successfully auto-generated just in time for the exam!")
                            config_row = fetch_config(input_config_id)
                            is_generated = config_row[8]
                        else:
                            st.error(f"Auto-generation error: {msg}")
                else:
                    st.warning("⚠️ Exam schedule time has arrived, but the Groq API Key is missing in the sidebar. Please enter your API key to enable auto-generation.")

            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT set_id, set_name, data, unlock_time, expires_at FROM paper_sets WHERE config_id = ?", (input_config_id,))
            available_sets = c.fetchall()
            conn.close()
            
            if available_sets:
                chosen_set = st.selectbox("Select Assigned Set Variant", available_sets, format_func=lambda x: f"{x[1]} (ID: {x[0]})")
                set_id, set_name, data_json, u_time, e_time = chosen_set
                
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT score, total_marks, agent_report, submitted_at FROM submissions WHERE student = ? AND set_id = ?", (student_name.strip(), set_id))
                prior_sub = c.fetchone()
                conn.close()
                
                if prior_sub:
                    p_score, p_total, p_report, p_time = prior_sub
                    st.warning(f"🔒 **Exam already submitted by {student_name.strip()} for {set_name} on {p_time}.** Answers are locked.")
                    st.metric("Recorded Final Score", f"{p_score} / {p_total}")
                    st.markdown("---")
                    st.markdown("### Diagnostic Evaluation Report")
                    st.markdown(p_report)
                else:
                    st.success(f"Session Active ({lang}) — **{set_name}** loaded successfully.")
                    questions = json.loads(data_json)
                    
                    with st.form("student_live_exam"):
                        student_answers = {}
                        for idx, q in enumerate(questions):
                            q_chapter = q.get('chapter', 'General')
                            q_level = q.get('level', 'Moderate')
                            q_text = q.get('q', '')
                            q_marks = int(q.get('marks', 1))
                            
                            st.markdown(f"**Q{idx+1}. [{q_chapter} | *{q_level}*] {q_text}** *({q_marks} Marks)*")
                            
                            if "options" in q and q["options"]:
                                opts = q["options"].copy()
                                student_answers[q['id']] = st.radio(f"Select choice {idx+1}", opts, key=f"ans_{set_id}_{q['id']}")
                            else:
                                student_answers[q['id']] = st.text_input(f"Answer {idx+1}", key=f"ans_{set_id}_{q['id']}")
                                
                        submitted_exam = st.form_submit_button("📤 Submit Final Examination (Locks Answers)", type="primary")
                        if submitted_exam:
                            if not api_key_input: st.error("Groq API Key required.")
                            else:
                                with st.spinner("Evaluating submissions and generating detailed diagnostic report..."):
                                    score = 0
                                    total_marks = 0
                                    evaluation_breakdown = []
                                    
                                    for idx, q in enumerate(questions):
                                        q_marks = int(q.get('marks', 1))
                                        total_marks += q_marks
                                        user_ans = str(student_answers.get(q['id'])).strip()
                                        correct_ans = str(q['correct']).strip()
                                        is_correct = user_ans.lower() == correct_ans.lower()
                                        if is_correct:
                                            score += q_marks
                                        
                                        evaluation_breakdown.append(
                                            f"- **Q{idx+1} ({q.get('chapter', 'General')}):** Given: `{user_ans}` | Correct: `{correct_ans}` | Result: {'✅ Correct' if is_correct else '❌ Incorrect'}"
                                        )
                                            
                                    try:
                                        eval_prompt = f"""
                                        Analyze this student exam submission thoroughly and provide a comprehensive diagnostic evaluation report in rich markdown (in language: {lang}):
                                        Student Name: {student_name}
                                        Score: {score} out of {total_marks} ({score/total_marks*100:.1f}%)
                                        Question Details & Answers:
                                        {chr(10).join(evaluation_breakdown)}

                                        Include sections:
                                        1. Executive Summary & Performance Grade
                                        2. Strengths & Topic Mastery
                                        3. Areas for Improvement & Conceptual Gaps
                                        4. Actionable Study Recommendations
                                        """
                                        agent_report = call_groq_llm(api_key_input, eval_prompt)
                                    except Exception as e:
                                        agent_report = f"""
### 📋 Detailed Diagnostic Evaluation Report ({lang})

* **Student Name:** {student_name}
* **Final Score:** **{score} / {total_marks}** ({score/total_marks*100:.1f}%)
* **Status:** Evaluated Successfully

---

#### 🔍 Question-by-Question Breakdown
{chr(10).join(evaluation_breakdown)}

---

#### 💡 Performance Summary
The student completed the assessment set. Review the incorrect responses above to identify specific chapters requiring targeted revision.
                                        """
                                        
                                    conn = get_db_connection()
                                    c = conn.cursor()
                                    c.execute("INSERT INTO submissions (student, set_id, score, total_marks, student_answers, agent_report, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                              (student_name.strip(), set_id, score, total_marks, json.dumps(student_answers, ensure_ascii=False), agent_report, str(get_ist_now())))
                                    conn.commit()
                                    conn.close()
                                    
                                    st.balloons()
                                    st.success(f"🎉 Exam Submitted & Locked! Final Score: **{score} / {total_marks}**")
                                    st.rerun()
            else: 
                st.warning("⚠️ Question sets are not yet generated. They will automatically synthesize once the exam schedule time is reached (or click **'Force Generate & Lock Sets Now'** in the Teacher Dashboard).")
        else: st.error("Invalid Configuration ID.")
    else:
        st.info("💡 Please enter your full name and a valid Assessment Config ID to access your exam paper.")

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
    st.write("Inspect or clear the raw underlying relational database tables directly inside the app interface for live presentation.")
    
    table_choice = st.selectbox("Select Database Table to Inspect", ["paper_configs", "paper_sets", "submissions"])
    
    col_insp1, col_insp2 = st.columns([3, 1])
    with col_insp2:
        if st.button("🗑️ Clear Selected Table", type="secondary"):
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(f"DELETE FROM {table_choice}")
            conn.commit()
            conn.close()
            st.success(f"Cleared all entries from `{table_choice}`!")
            st.rerun()

    conn = get_db_connection()
    try:
        df = pd.read_sql_query(f"SELECT * FROM {table_choice}", conn)
        st.metric(f"Total Rows in `{table_choice}`", len(df))
        st.dataframe(df, use_container_width=True)
    except Exception:
        st.info(f"Table `{table_choice}` is currently empty. Run an action in the Teacher or Student portal first!")
    finally:
        conn.close()
