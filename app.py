import streamlit as st
import psycopg2
import json
import random
from datetime import datetime, timedelta
from google import genai

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="TestGen-Agent Pro",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MODERN UI CUSTOM STYLING ---
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .stButton>button {
        width: 100%;
        border-radius: 6px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    .stButton>button:hover {
        border-color: #2563eb;
        color: #2563eb;
    }
    div.block-container { padding-top: 2rem; }
    .metric-card {
        background: white;
        padding: 1.2rem;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        border: 1px solid #e2e8f0;
    }
    </style>
""", unsafe_allow_html=True)

# --- DATABASE CONNECTION (SUPABASE POSTGRESQL) ---
def get_db_connection():
    try:
        return psycopg2.connect(st.secrets["SUPABASE_URL"])
    except Exception as e:
        st.error(f"Database Connection Error: Check your Supabase configuration in Secrets. Details: {e}")
        st.stop()

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS paper_configs 
                 (config_id TEXT PRIMARY KEY, category TEXT, board_stream TEXT, grade TEXT, subject TEXT, matrix_data TEXT, num_sets INTEGER, exam_time TEXT, generated INT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS paper_sets 
                 (set_id TEXT PRIMARY KEY, config_id TEXT, set_name TEXT, data TEXT, unlock_time TEXT, expires_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS submissions 
                 (id SERIAL PRIMARY KEY, student TEXT, set_id TEXT, score REAL, total_marks REAL, student_answers TEXT, agent_report TEXT, submitted_at TEXT)''')
    conn.commit()
    c.close()
    conn.close()

init_db()

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.image("https://img.icons8.com/clouds/200/graduation-cap.png", width=100)
    st.title("TestGen-Agent")
    st.caption("Autonomous Academic Intelligence")
    
    st.markdown("---")
    api_key_input = st.text_input("🔑 Gemini API Key", type="password", help="Enter your Gemini API key for agentic generation and evaluation.")
    
    st.markdown("---")
    role = st.selectbox("🧭 Navigation Portal", ["Teacher Dashboard", "Student Examination Portal", "Analytics & Reports Hub"])
    
    st.markdown("---")
    st.info("💡 **Tip:** Use the Agentic Auto-Discover options in the Teacher Dashboard to fetch official syllabi instantly.")

# --- HELPER FUNCTION: JIT GENERATION ---
def run_jit_generation(config_id, api_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time FROM paper_configs WHERE config_id = ?", (config_id,))
    # Note: Using parameterized SQL syntax compatible with psycopg2 placeholders (%s) or standard formats. 
    # Let's adjust queries safely for PostgreSQL placeholders %s below.
    pass

# Safe PostgreSQL helper for fetching config
def fetch_config(config_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated FROM paper_configs WHERE config_id = %s", (config_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    return row

def run_jit_generation_pg(config_id, api_key):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT category, board_stream, grade, subject, matrix_data, num_sets, exam_time FROM paper_configs WHERE config_id = %s", (config_id,))
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
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:-3].strip()
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:-3].strip()
            
            parsed_q = json.loads(raw_text)
            expire_dt = scheduled_dt + timedelta(hours=3)
            
            c.execute("INSERT INTO paper_sets (set_id, config_id, set_name, data, unlock_time, expires_at) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (set_id) DO UPDATE SET data = EXCLUDED.data",
                      (set_id, config_id, set_name, json.dumps(parsed_q), exam_time_str, str(expire_dt)))
                      
        c.execute("UPDATE paper_configs SET generated = 1 WHERE config_id = %s", (config_id,))
        conn.commit()
        c.close()
        conn.close()
        return True, "Success"
    except Exception as e:
        if conn:
            conn.close()
        return False, str(e)


# ==========================================
# 1. TEACHER PORTAL
# ==========================================
if role == "Teacher Dashboard":
    st.header("📋 Teacher Dashboard: Autonomous Curriculum & Blueprint Hub")
    st.write("Configure institutional streams, map verified exam boards, and launch AI-driven synchronized question sheets.")
    
    with st.container():
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
        if api_key_input and st.button("🤖 Discover Official Subjects via Gemini"):
            with st.spinner("Querying active board frameworks..."):
                try:
                    client = genai.Client(api_key=api_key_input)
                    prompt = f"List official core subjects for Category: {category}, Board/Stream: {board_stream}, Level: {grade}. Return ONLY a raw JSON array of strings: [\"Subject 1\", \"Subject 2\"]."
                    res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    clean_res = res.text.strip()
                    if clean_res.startswith("```json"): clean_res = clean_res[7:-3].strip()
                    elif clean_res.startswith("```"): clean_res = clean_res[3:-3].strip()
                    st.session_state.fetched_subjects = json.loads(clean_res)
                    st.success("Official subjects discovered successfully!")
                except Exception as e:
                    st.error(f"Discovery error: {e}")

        if "fetched_subjects" in st.session_state and st.session_state.fetched_subjects:
            subject = st.selectbox("Select Discovered Subject", st.session_state.fetched_subjects)
        else:
            subject = st.text_input("Core Subject Name", "Mathematics")

    st.markdown("---")
    st.subheader("⚙️ Section Blueprint & Chapter Matrix")
    
    col_info, col_act = st.columns([3, 1])
    with col_info:
        st.markdown("Define chapters, weightages, and item variants manually or fetch via the official curriculum map.")
    with col_act:
        if api_key_input and st.button("✨ Auto-Populate Matrix"):
            with st.spinner("Extracting standard syllabus matrix..."):
                try:
                    client = genai.Client(api_key=api_key_input)
                    prompt = f"""
                    Provide official chapters and key topic units for Board: {board_stream}, Grade: {grade}, Subject: {subject}.
                    Return ONLY a raw JSON array of objects with keys 'chapter' and 'topics' (as a comma-separated string):
                    [{{"chapter": "Chapter Name 1", "topics": "Topic A, Topic B"}}]
                    """
                    res = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
                    clean_res = res.text.strip()
                    if clean_res.startswith("```json"): clean_res = clean_res[7:-3].strip()
                    elif clean_res.startswith("```"): clean_res = clean_res[3:-3].strip()
                    discovered_matrix = json.loads(clean_res)
                    
                    st.session_state.matrix_rows = []
                    for item in discovered_matrix:
                        st.session_state.matrix_rows.append({
                            "chapter": item.get("chapter", ""),
                            "topics": item.get("topics", ""),
                            "q_type": "MCQ",
                            "count": 2,
                            "marks": 2
                        })
                    st.success("Syllabus mapped!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Mapping failed: {e}")

    if "matrix_rows" not in st.session_state:
        st.session_state.matrix_rows = [{"chapter": "", "topics": "", "q_type": "MCQ", "count": 2, "marks": 2}]

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
            mks = st.number_input(f"Marks {idx+1}", min_value=1, value=row["marks"], key=f"mks_{idx}")
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
    with col_s1:
        num_sets = st.slider("Parallel Anti-Cheating Randomized Sets", 1, 4, 3)
    with col_s2:
        exam_date = st.date_input("Exam Date")
        exam_time = st.time_input("Exam Start Time")
        
    scheduled_dt_str = f"{exam_date} {exam_time}"
    
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        if st.button("🚀 Schedule Exam Blueprint", type="primary"):
            if not api_key_input:
                st.error("API Key required.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT INTO paper_configs (config_id, category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)",
                          (config_id, category, board_stream, grade, subject, json.dumps(matrix_input_data), num_sets, scheduled_dt_str))
                conn.commit()
                c.close()
                conn.close()
                st.success(f"✅ Config scheduled successfully! Config ID: **{config_id}**")
                
    with b_col2:
        if st.button("⚡ Force Generate & Lock Sets Now"):
            if not api_key_input:
                st.error("API Key required.")
            else:
                config_id = f"CFG_{subject[:3].upper()}_{random.randint(1000,9999)}"
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("INSERT INTO paper_configs (config_id, category, board_stream, grade, subject, matrix_data, num_sets, exam_time, generated) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)",
                          (config_id, category, board_stream, grade, subject, json.dumps(matrix_input_data), num_sets, scheduled_dt_str))
                conn.commit()
                c.close()
                conn.close()
                
                with st.spinner("Synthesizing multi-set question banks..."):
                    success, msg = run_jit_generation_pg(config_id, api_key_input)
                    if success:
                        st.success(f"🔥 Successfully generated! Config ID: **{config_id}**")
                    else:
                        st.error(f"Generation error: {msg}")

# ==========================================
# 2. STUDENT PORTAL
# ==========================================
elif role == "Student Examination Portal":
    st.header("📝 Student Assessment Portal")
    st.write("Enter your credentials and config key to launch your secure real-time test environment.")
    
    col_login1, col_login2 = st.columns(2)
    with col_login1:
        student_name = st.text_input("Full Name", "Alex Morgan")
    with col_login2:
        input_config_id = st.text_input("Assessment Config ID")
        
    if input_config_id:
        config_row = fetch_config(input_config_id)
        if config_row:
            cat, b_stream, grd, subj, matrix_json, n_sets, exam_time_str, is_generated = config_row
            scheduled_dt = datetime.strptime(exam_time_str, "%Y-%m-%d %H:%M:%S")
            jit_trigger_dt = scheduled_dt - timedelta(minutes=2)
            current_time = datetime.now()
            
            if current_time >= jit_trigger_dt and is_generated == 0:
                if api_key_input:
                    run_jit_generation_pg(input_config_id, api_key_input)
                    config_row = fetch_config(input_config_id)
                    is_generated = config_row[7]

            if current_time < jit_trigger_dt:
                st.warning(f"⏳ Assessment is locked until **{exam_time_str}**.")
            elif is_generated == 0:
                st.error("⚠️ Assessment configuration awaiting activation key sync.")
            else:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT set_id, set_name, data, unlock_time, expires_at FROM paper_sets WHERE config_id = %s", (input_config_id,))
                available_sets = c.fetchall()
                c.close()
                conn.close()
                
                if available_sets:
                    chosen_set = st.selectbox("Select Assigned Set Variant", available_sets, format_func=lambda x: f"{x[1]} (ID: {x[0]})")
                    set_id, set_name, data_json, u_time, e_time = chosen_set
                    
                    if datetime.now() > datetime.strptime(e_time, "%Y-%m-%d %H:%M:%S"):
                        st.error("❌ Assessment submission window has expired.")
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
                                if not api_key_input:
                                    st.error("API Key required for evaluation.")
                                else:
                                    with st.spinner("Evaluating submissions..."):
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
                                            Provide a detailed diagnostic performance review with strengths and chapter-wise feedback in clear markdown.
                                            """
                         
