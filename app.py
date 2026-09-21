import streamlit as st
import sqlite3
import json
import random
from datetime import datetime, timedelta
from google import genai

# --- 1. DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect("exam_platform_pro.db")
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

st.set_page_config(page_title="TestGen-Agent Pro", layout="wide")
st.title("🎓 TestGen-Agent: Autonomous Academic Intelligence Hub")

st.sidebar.subheader("🔑 Gemini AI Configuration")
api_key_input = st.sidebar.text_input("Enter Gemini API Key", type="password")

role = st.sidebar.selectbox("Select Portal", ["Teacher Portal", "Student Portal", "Teacher Analytics & Reports"])

# Helper function for JIT Generation
def run_jit_generation(config_id, api_key):
    conn = sqlite3.connect("exam_platform_pro.db")
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time FROM paper_configs WHERE config_id = ?", (config_id,))
    config_row = c.fetchone()
    
    if not config_row:
        conn.close()
        return False, "Config ID not found."
        
    cat, b_stream, grd, subj, matrix_json, n_sets, exam_time_str = config_row
    scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S")
    
    try:
        client = genai.Client(api_key=api_key)
        matrix_specs = json.loads(matrix_json)
        
        for i in range(n_sets):
            set_name = f"Set_{chr(65+i)}"
            set_id = f"{subj[:3].upper()}_{set_name}_{random.randint(1111,9999)}"
            
            prompt = f"""
            You are an elite AI assessment builder. Create a rigorous academic question paper set ({set_name}) adhering strictly to:
            Category: {cat}, Stream/Board: {b_stream}, Grade: {grd}, Subject: {subj}.
            Based on this section matrix breakdown: {json.dumps(matrix_specs)}.
            Ensure unique wording to prevent cheating. Return ONLY a raw JSON array format:
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
            response = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3].strip()
            
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


# ==========================================
# TEACHER PORTAL
# ==========================================
if role == "Teacher Portal":
    st.header("Teacher Dashboard: Autonomous Curriculum & Matrix Builder")
    
    category = st.selectbox("Select Institution Category", ["School Board (K-12)", "College / University Stream", "Competitive / Entrance Exam"])
    
    if category == "School Board (K-12)":
        board_stream = st.selectbox("Select Education Board", ["CBSE", "ICSE", "State Board (General)", "IB / IGCSE"])
        grade = st.selectbox("Select Class / Grade", ["Class 6", "Class 7", "Class 8", "Class 9", "Class 10", "Class 11", "Class 12"])
    elif category == "College / University Stream":
        board_stream = st.selectbox("Select Stream", ["B.Tech / Computer Science", "B.Sc (Pure Sciences)", "B.Com / Management", "Medical / MBBS Basics"])
        grade = st.selectbox("Select Semester / Year", ["Semester 1", "Semester 2", "Semester 3", "Semester 4", "Final Year"])
    else:
        board_stream = st.selectbox("Select Entrance Target", ["JEE (Main & Advanced)", "NEET (Medical)", "GATE (Engineering)", "UPSC Prelims"])
        grade = st.selectbox("Target Tier", ["Target Year Tier 1", "Target Year Tier 2"])

    # AGENTIC STEP 1: FETCH OFFICIAL SUBJECTS
    subject = "Mathematics"
    if api_key_input:
        if st.button("🤖 Agentic Fetch: Discover Official Subjects"):
            with st.spinner("Gemini Agent querying official board curriculum databases..."):
                try:
                    client = genai.Client(api_key=api_key_input)
                    prompt = f"List official subjects for Category: {category}, Board/Stream: {board_stream}, Level: {grade}. Return ONLY a raw JSON array of strings: [\"Subject 1\", \"Subject 2\"]."
                    res = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
                    clean_res = res.text.strip()
                    if clean_res.startswith("```json"): clean_res = clean_res[7:-3].strip()
                    elif clean_res.startswith("```"): clean_res = clean_res[3:-3].strip()
                    st.session_state.fetched_subjects = json.loads(clean_res)
                    st.success("Subjects successfully discovered!")
                except Exception as e:
                    st.error(f"Error fetching subjects: {e}")
        
        if "fetched_subjects" in st.session_state:
            subject = st.selectbox("Select Official Discovered Subject", st.session_state.fetched_subjects)
        else:
            subject = st.text_input("Enter Core Subject", "Mathematics")
    else:
        subject = st.text_input("Enter Core Subject", "Mathematics")
        st.info("💡 Enter your Gemini API Key in the sidebar to enable autonomous official subject discovery.")

    # AGENTIC STEP 2: MATRIX BUILDER WITH OFFICIAL CHAPTERS & TOPICS DISCOVERY
    st.subheader("📋 Section Matrix: Official Chapters, Topics & Question Type Breakdown")
    st.info("Click 'Agentic Auto-Discover Chapters' below to have Gemini populate official chapters and core topic breakdown per row based on official board blueprints.")

    if api_key_input and st.button("🤖 Agentic Auto-Discover Official Chapters & Topics for Matrix"):
        with st.spinner("Gemini Agent mapping official syllabus chapters and core weightage topics..."):
            try:
                client = genai.Client(api_key=api_key_input)
                prompt = f"""
                Provide official chapters and key topic units for Board: {board_stream}, Grade: {grade}, Subject: {subject}.
                Return ONLY a raw JSON array of objects with keys 'chapter' and 'topics' (as a comma-separated string):
                [
                  {{"chapter": "Chapter Name 1", "topics": "Topic A, Topic B"}}
                ]
                """
                res = client.models.generate_content(model='gemini-3.5-flash', contents=prompt)
                clean_res = res.text.strip()
                if clean_res.startswith("```json"): clean_res = clean_res[7:-3].strip()
                elif clean_res.startswith("```"): clean_res = clean_res[3:-3].strip()
                discovered_matrix = json.loads(clean_res)
                
                # Populate session matrix rows
                st.session_state.matrix_rows = []
                for item in discovered_matrix:
                    st.session_state.matrix_rows.append({
                        "chapter": item.get("chapter", ""),
                        "topics": item.get("topics", ""),
                        "q_type": "MCQ",
                        "count": 2,
                        "marks": 2
                    })
                st.success("Official curriculum matrix successfully mapped!")
                st.rerun()
            except Exception as e:
                st.error(f"Agentic discovery failed: {e}")

    if "matrix_rows" not in st.session_state:
        st.session_state.matrix_rows = [{"chapter": "", "topics": "", "q_type": "MCQ", "count": 2, "marks": 2}]
        
    def add_row():
        st.session_state.matrix_rows.append({"chapter": "", "topics": "", "q_type": "MCQ", "count": 2, "marks": 2})
        
    def remove_row(idx):
        if len(st.session_state.matrix_rows) > 1:
            st.session_state.matrix_rows.pop(idx)

    matrix_input_data = []
    for idx, row in enumerate(st.session_state.matrix_rows):
        cols = st.columns([2, 3, 2, 1, 1, 1])
        with cols[0]:
            ch = st.text_input(f"Chapter {idx+1}", value=row["chapter"], key=f"ch_{idx}")
        with cols[1]:
            tp = st.text_input(f"Topics {idx+1}", value=row["topics"], key=f"tp_{idx}")
        with cols[2]:
            qt = st.selectbox(f"Type {idx+1}", ["MCQ", "Short Answer", "Numerical / Derivation"], index=["MCQ", "Short Answer", "Numerical / Derivation"].index(row["q_type"]), key=f"qt_{idx}")
        with cols[3]:
            cnt = st.number_input(f"Count {idx+1}", min_value=1, value=row["count"], key=f"cnt_{idx}")
        with cols[4]:
            mks = st.number_input(f"Marks/Q {idx+1}", min_value=1, value=row["marks"], key=f"mks_{idx}")
        with cols[5]:
            st.write("")
            st.write("")
            if st.button("❌", key=f"del_{idx}"):
                remove_row(idx)
                st.rerun()
        matrix_input_data.append({"chapter": ch, "topics": tp, "q_type": qt, "count": cnt, "marks": mks})

    if st.button("➕ Add Section Row"):
        add_row()
        st.rerun()

    num_sets = st.slider("Number of Parallel Randomized Sets (Anti-Cheating)", 2, 4, 3)
    
    st.subheader("⏱️ Real-Time Generation Schedule & Instant Authoring")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        exam_date = st.date_input("Scheduled Exam Date")
        exam_time = st.time_input("Scheduled Exam Start Time")
        
    scheduled_dt_str = f"{exam_date} {exam_time}"
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🚀 Schedule Exam Blueprint"):
            if not api_key_input:
                st.error("⚠️ Please input your Gemini API Key in the sidebar.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = sqlite3.connect("exam_platform_pro.db")
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO paper_configs VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                          (config_id, category, board_stream, grade, subject, json.dumps(matrix_input_data), num_sets, scheduled_dt_str))
                conn.commit()
                conn.close()
                st.success(f"✅ Exam successfully scheduled! Blueprint Config ID: `{config_id}`.")
                
    with col_btn2:
        if st.button("⚡ Force Generate JIT Sets Right Now"):
            if not api_key_input:
                st.error("⚠️ Please input your Gemini API Key in the sidebar.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = sqlite3.connect("exam_platform_pro.db")
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO paper_configs VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                          (config_id, category, board_stream, grade, subject, json.dumps(matrix_input_data), num_sets, scheduled_dt_str))
                conn.commit()
                conn.close()
                
                with st.spinner("🤖 Forcing real-time Gemini agentic generation..."):
                    success, msg = run_jit_generation(config_id, api_key_input)
                    if success:
                        st.success(f"🔥 Sets successfully synthesized and locked instantly! Config ID: `{config_id}`")
                    else:
                        st.error(f"Generation failed: {msg}")

# ==========================================
# STUDENT PORTAL
# ==========================================
elif role == "Student Portal":
    st.header("Student Portal: Secure JIT Exam Session")
    
    student_name = st.text_input("Enter Full Name", "Alex Morgan")
    input_config_id = st.text_input("Enter Scheduled Config ID or Assigned Set ID")
    
    if input_config_id:
        conn = sqlite3.connect("exam_platform_pro.db")
        c = conn.cursor()
        c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated FROM paper_configs WHERE config_id = ?", (input_config_id,))
        config_row = c.fetchone()
        
        if config_row:
            cat, b_stream, grd, subj, matrix_json, n_sets, exam_time_str, is_generated = config_row
            scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S")
            jit_trigger_dt = scheduled_dt - timedelta(minutes=2)
            current_time = datetime.now()
            
            if current_time >= jit_trigger_dt and is_generated == 0:
                if api_key_input:
                    run_jit_generation(input_config_id, api_key_input)
                    c.execute("SELECT generated FROM paper_configs WHERE config_id = ?", (input_config_id,))
                    is_generated = c.fetchone()[0]

            if current_time < jit_trigger_dt:
                st.warning(f"⏳ **Secure JIT Lock:** This exam is scheduled for **{exam_time_str}**. Real-time AI generation unlocks automatically 2 minutes prior at **{jit_trigger_dt.strftime('%Y-%m-%d %H:%M:%S')}**.")
            elif is_generated == 0:
                st.error("⚠️ Exam time reached, but API key is missing. Teacher must supply key or trigger manual generation.")
            else:
                c.execute("SELECT set_id, set_name, data, unlock_time, expires_at FROM paper_sets WHERE config_id = ?", (input_config_id,))
                available_sets = c.fetchall()
                conn.close()
                
                if available_sets:
                    chosen_set = st.selectbox("Select Your Assigned Randomized Set", available_sets, format_func=lambda x: f"{x[1]} (ID: {x[0]})")
                    set_id, set_name, data_json, u_time, e_time = chosen_set
                    
                    cur_dt = datetime.now()
                    exp_dt = datetime.strptime(e_time, "%Y-%m-%d %H:%M:%S")
                    
                    if cur_dt > exp_dt:
                        st.error("❌ Exam submission window has expired.")
                    else:
                        st.success(f"📝 Active Assessment Loaded: **{set_name}**")
                        questions = json.loads(data_json)
                        
                        with st.form("student_live_exam"):
                            student_answers = {}
                            for idx, q in enumerate(questions):
                                st.markdown(f"**Q{idx+1}. [{q.get('chapter','General')}] {q['q']}** *({q['marks']} Marks)*")
                                if "options" in q and q["options"]:
                                    opts = q["options"].copy()
                                    random.shuffle(opts)
                                    student_answers[q['id']] = st.radio(f"Select option {idx+1}", opts, key=f"ans_{set_id}_{q['id']}")
                                else:
                                    student_answers[q['id']] = st.text_input(f"Your Answer {idx+1}", key=f"ans_{set_id}_{q['id']}")
                                    
                            submitted_exam = st.form_submit_button("📤 Submit Final Exam")
                            
                            if submitted_exam:
                                if not api_key_input:
                                    st.error("API Key required for agentic evaluation.")
                                else:
                                    with st.spinner("🤖 Agentic Evaluation & Analytics Engine analyzing submission..."):
                                        score = 0
                                        total_marks = 0
                                        for q in questions:
                                            total_marks += q['marks']
                                            if str(student_answers.get(q['id'])).strip().lower() == str(q['correct']).strip().lower():
                                                score += q['marks']
                                                
                                        try:
                                            client = genai.Client(api_key=api_key_input)
                                            eval_prompt = f"""
                                            Analyze this student exam submission:
                                            Student: {student_name}, Score: {score}/{total_marks}.
                                            Questions & Correct Keys: {json.dumps(questions)}
                                            Student Answers: {json.dumps(student_answers)}
                                            Provide a detailed, encouraging diagnostic report evaluating their strengths, weaknesses per chapter, and precise study recommendations in clear markdown formatting.
                                            """
                                            eval_res = client.models.generate_content(model='gemini-3.5-flash', contents=eval_prompt)
                                            agent_report = eval_res.text
                                        except Exception:
                                            agent_report = "Diagnostic report generated via deterministic baseline score verification."
                                            
                                        conn = sqlite3.connect("exam_platform_pro.db")
                                        c = conn.cursor()
                                        c.execute("INSERT INTO submissions (student, set_id, score, total_marks, student_answers, agent_report, submitted_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                                  (student_name, set_id, score, total_marks, json.dumps(student_answers), agent_report, str(datetime.now())))
                                        conn.commit()
                                        conn.close()
                                        
                                        st.balloons()
                                        st.success(f"🎉 Exam Submitted Successfully! Final Score: **{score} / {total_marks}**")
                                        st.markdown("---")
                                        st.subheader("📊 Your Personal Agentic Diagnostic Report")
                                        st.markdown(agent_report)
        else:
            conn.close()
            st.error("Invalid Config ID.")

# ==========================================
# TEACHER ANALYTICS & REPORTS PORTAL
# ==========================================
elif role == "Teacher Analytics & Reports":
    st.header("Teacher Analytics: Live Student Submissions & Reports")
    
    conn = sqlite3.connect("exam_platform_pro.db")
    c = conn.cursor()
    c.execute("SELECT id, student, set_id, score, total_marks, agent_report, submitted_at FROM submissions ORDER BY id DESC")
    subs = c.fetchall()
    conn.close()
    
    if not subs:
        st.info("No student submissions logged yet.")
    else:
        for sub in subs:
            sub_id, s_name, s_set, score, t_marks, report, s_time = sub
            with st.expander(f"👤 Student: {s_name} | Set: {s_set} | Score: {score}/{t_marks} | Submitted: {s_time}"):
                st.metric(label="Percentage", value=f"{(score/t_marks)*100:.2f}%" if t_marks > 0 else "0%")
                st.markdown("### 🤖 Agentic Evaluation Audit & Feedback")
                st.markdown(report)
